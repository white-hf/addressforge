from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from addressforge.core.common import (
    build_base_address_key,
    build_full_address_key,
    canonicalize_unit_number,
    fetch_all,
    hybrid_canadian_parse_address,
    infer_structure_type,
    libpostal_parse_address,
    normalize_city,
    normalize_province,
    normalize_space,
    normalize_street_name,
    simple_parse_address,
)
from addressforge.core.utils import logger
from addressforge.core.reference import GeoNovaReferenceMatcher
from addressforge.core.config import ADDRESSFORGE_MODEL_FAMILY, ADDRESSFORGE_WORKSPACE_NAME
from addressforge.models import bootstrap_default_registry, get_active_model, get_model, list_models, list_workspaces
from addressforge.core.profiles.factory import get_profile
from addressforge.learning import (
    count_active_learning_queue,
    count_gold_labels,
    freeze_gold_set,
    list_active_learning_queue,
    list_gold_labels,
    list_gold_snapshots,
    seed_active_learning_queue,
    upsert_gold_label,
)


APP_TITLE = "Address Platform API / 地址平台 API"
API_VERSION = "v1"
DEFAULT_MODEL_PROFILE = os.getenv("ADDRESSFORGE_DEFAULT_PROFILE", os.getenv("ADDRESS_PLATFORM_DEFAULT_PROFILE", "base_canada"))
PLATFORM_VERSION = os.getenv("ADDRESSFORGE_PROJECT_VERSION", os.getenv("ADDRESS_PLATFORM_VERSION", "AddressForge.0.0"))
MODEL_VERSION = os.getenv("ADDRESSFORGE_MODEL_VERSION", os.getenv("ADDRESS_PLATFORM_MODEL_VERSION", "canada_default_v1"))
REFERENCE_VERSION = os.getenv("ADDRESSFORGE_REFERENCE_VERSION", os.getenv("ADDRESS_PLATFORM_REFERENCE_VERSION", "geonova_current"))
SUPPORTED_PROFILES = ("base_canada", "north_america_default", "custom")
DEFAULT_PARSERS = ("simple_rule", "hybrid_canada", "libpostal")


class AddressRequest(BaseModel):
    raw_address_text: str = Field(..., description="Raw address text")
    city: str | None = None
    province: str | None = None
    postal_code: str | None = None
    country_code: str = Field(default="CA", description="Country code")
    latitude: float | None = None
    longitude: float | None = None
    profile: str = Field(default=DEFAULT_MODEL_PROFILE, description="Model profile")
    parsers: list[str] | None = Field(default=None, description="Parser names to use")
    reranker_version: str | None = Field(default=None, description="Optional model/reranker version to load parser weights from")


class ExplainRequest(AddressRequest):
    include_steps: bool = True


class GoldLabelRequest(BaseModel):
    workspace_name: str = Field(default=ADDRESSFORGE_WORKSPACE_NAME)
    source_name: str = Field(default="human")
    source_id: str = Field(..., description="Stable source identifier")
    task_type: str = Field(default="validation")
    label_json: Any = Field(default_factory=dict)
    review_status: str = Field(default="accepted")
    label_source: str = Field(default="human")
    score: float | None = None
    notes: str | None = None


class GoldFreezeRequest(BaseModel):
    workspace_name: str = Field(default=ADDRESSFORGE_WORKSPACE_NAME)
    gold_set_version: str = Field(default="gold_v1")
    split_version: str = Field(default="v1")
    label_source_filter: str = Field(default="human")
    task_type: str | None = None
    notes: str | None = None


class ActiveLearningSeedRequest(BaseModel):
    workspace_name: str = Field(default=ADDRESSFORGE_WORKSPACE_NAME)
    limit: int = Field(default=250, ge=1)
    confidence_threshold: float = Field(default=0.55, ge=0.0, le=1.0)


@dataclass(frozen=True)
class CandidateView:
    parser_name: str
    parser_version: str
    score: float
    parsed: dict[str, Any]
    match_rules: list[str]


def _score_candidate(parsed: dict[str, Any], *, parser_name: str | None = None, parser_weights: dict[str, Any] | None = None) -> float:
    parse_confidence = float(parsed.get("parse_confidence") or 0.0)
    unit_confidence = float(parsed.get("unit_confidence") or 0.0)
    postal_confidence = float(parsed.get("postal_confidence") or 0.0)
    base_score = 0.70 * parse_confidence + 0.20 * unit_confidence + 0.10 * postal_confidence
    if parsed.get("street_number") and parsed.get("street_name"):
        base_score += 0.05
    if parsed.get("postal_code"):
        base_score += 0.03
    if parser_name and isinstance(parser_weights, dict):
        try:
            parser_weight = float(parser_weights.get(parser_name) or 0.0)
            base_score += min(max(parser_weight, 0.0), 1.0) * 0.03
        except (TypeError, ValueError):
            pass
    return round(min(base_score, 0.99), 4)


class RerankerArtifactLoader:
    @staticmethod
    def load_weights(workspace_name: str, *, version: str | None = None) -> dict[str, Any]:
        model_row: dict[str, Any] | None = None
        if version:
            rows = fetch_all(
                """
                SELECT *
                FROM model_registry
                WHERE workspace_name = %s AND model_version = %s
                ORDER BY is_default DESC, updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (workspace_name, version),
            )
            model_row = rows[0] if rows else None
        else:
            model_row = get_active_model(workspace_name)
        if not model_row:
            return {}
        artifact_path = model_row.get("artifact_path")
        if not artifact_path:
            return {}
        artifact_file = Path(str(artifact_path))
        if not artifact_file.exists():
            return {}
        try:
            artifact = json.loads(artifact_file.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load reranker artifact from %s: %s", artifact_path, exc)
            return {}
        decision_policy = artifact.get("decision_policy")
        if not isinstance(decision_policy, dict):
            return {}
        weights = decision_policy.get("parser_weights")
        return weights if isinstance(weights, dict) else {}

def _parser_candidates(
    request: AddressRequest,
    *,
    default_profile: str | None = None,
    default_parsers: tuple[str, ...] = DEFAULT_PARSERS,
    parser_weights: dict[str, Any] | None = None,
) -> list[CandidateView]:
    raw_text = normalize_space(request.raw_address_text)
    parser_names = tuple(request.parsers or default_parsers)
    candidates: list[CandidateView] = []
    
    profile = get_profile(request.profile or default_profile or request.country_code or "CA")

    parser_map = {
        "simple_rule": ("v1", simple_parse_address),
        "hybrid_canada": ("v1", hybrid_canadian_parse_address),
        "libpostal": ("native_v1", libpostal_parse_address),
    }
    for parser_name in parser_names:
        entry = parser_map.get(parser_name)
        if not entry:
            continue
        parser_version, parser_fn = entry
        
        # Inject runtime profile into parser functions
        # 向解析器函数注入运行时配置文件
        parsed = parser_fn(
            raw_text,
            profile=profile,
            fallback_postal=request.postal_code,
            fallback_city=request.city,
            fallback_province=request.province,
        )
        parsed = dict(parsed)

        if parser_name == "simple_rule" and "parse_confidence" not in parsed:
            parsed["parse_confidence"] = 0.85 if parsed.get("street_number") and parsed.get("street_name") else 0.25
            parsed["unit_confidence"] = 0.85 if parsed.get("unit_number") else 0.10
            parsed["postal_confidence"] = 0.90 if parsed.get("postal_code") else 0.20
        parsed.setdefault("city", normalize_city(request.city))
        parsed.setdefault("province", normalize_province(request.province, profile))
        parsed.setdefault("postal_code", request.postal_code)
        score = _score_candidate(parsed, parser_name=parser_name, parser_weights=parser_weights)
        rules = [parser_name]
        if parsed.get("unit_source"):
            rules.append(str(parsed["unit_source"]))
        candidates.append(
            CandidateView(
                parser_name=parser_name,
                parser_version=parser_version,
                score=score,
                parsed=parsed,
                match_rules=rules,
            )
        )
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates


class AddressPlatformService:
    def __init__(
        self,
        *,
        default_profile: str | None = None,
        default_parsers: tuple[str, ...] | None = None,
        decision_policy: dict[str, Any] | None = None,
    ) -> None:
        self._reference_matcher = GeoNovaReferenceMatcher()
        self._default_profile = default_profile or DEFAULT_MODEL_PROFILE
        self._default_parsers = default_parsers or DEFAULT_PARSERS
        self._decision_policy = decision_policy or {}

    def _policy_float(self, key: str, default: float) -> float:
        value = self._decision_policy.get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _parser_weights(self) -> dict[str, Any]:
        value = self._decision_policy.get("parser_weights") or {}
        return value if isinstance(value, dict) else {}

    def model_info(self) -> dict[str, Any]:
        reference_count = 0
        try:
            from addressforge.core.common import fetch_all

            try:
                rows = fetch_all(
                    "SELECT COUNT(*) AS cnt FROM external_building_reference WHERE workspace_name = %s AND is_active = 1",
                    (ADDRESSFORGE_WORKSPACE_NAME,),
                )
            except Exception:
                rows = fetch_all("SELECT COUNT(*) AS cnt FROM external_building_reference WHERE is_active = 1")
            reference_count = int(rows[0]["cnt"]) if rows else 0
        except Exception as exc:  # noqa: BLE001
            logger.warning("Model info reference count unavailable: %s", exc)
        workspace_name = ADDRESSFORGE_WORKSPACE_NAME
        workspace = None
        active_model = None
        model_count = 0
        try:
            snapshot = bootstrap_default_registry()
            workspace = snapshot.get("workspace")
            active_model = snapshot.get("model")
            workspace_name = str(workspace.get("workspace_name") or workspace_name) if workspace else workspace_name
            model_count = len(list_models(workspace_name))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Model registry unavailable: %s", exc)
            try:
                active_model = get_active_model(workspace_name)
                model_count = len(list_models(workspace_name))
            except Exception as inner_exc:  # noqa: BLE001
                logger.warning("Model registry fallback unavailable: %s", inner_exc)
        return {
            "platform_version": PLATFORM_VERSION,
            "api_version": API_VERSION,
            "default_model_profile": self._default_profile,
            "workspace_name": workspace_name,
            "supported_profiles": list(SUPPORTED_PROFILES),
            "default_parsers": list(self._default_parsers),
            "model_name": active_model.get("model_name") if active_model else os.getenv("ADDRESSFORGE_MODEL_NAME", "canada_default"),
            "model_version": active_model.get("model_version") if active_model else MODEL_VERSION,
            "model_family": active_model.get("model_family") if active_model else ADDRESSFORGE_MODEL_FAMILY,
            "reference_version": REFERENCE_VERSION,
            "reference_count": reference_count,
            "model_count": model_count,
            "active_model": active_model,
            "capabilities": [
                "normalize",
                "parse",
                "validate",
                "explain",
                "model_info",
                "gold_management",
                "active_learning",
            ],
            "open_source": True,
            "self_hosted": True,
        }

    def normalize(self, request: AddressRequest) -> dict[str, Any]:
        profile = get_profile(request.profile or self._default_profile or request.country_code or "CA")
        raw_text = normalize_space(request.raw_address_text)
        parsed = simple_parse_address(
            raw_text,
            profile=profile,
            fallback_postal=request.postal_code,
            fallback_city=request.city,
            fallback_province=request.province,
            country_code=request.country_code,
        )
        normalized_city = normalize_city(request.city) or parsed["city"]
        normalized_province = normalize_province(request.province, profile) or parsed["province"]
        result = {
            "profile": request.profile or self._default_profile,
            "raw_address_text": raw_text,
            "normalized_text": parsed["normalized_text"],
            "normalized_city": normalized_city,
            "normalized_province": normalized_province,
            "normalized_postal_code": parsed["postal_code"],
            "text_fingerprint": parsed["base_address_key"],
            "normalization_flags": [],
            "country_code": request.country_code or "CA",
        }
        flags = result["normalization_flags"]
        if request.postal_code:
            flags.append("postal_provided")
        if request.city:
            flags.append("city_provided")
        if request.province:
            flags.append("province_provided")
        if result["normalized_postal_code"]:
            flags.append("postal_detected")
        return result

    def parse(self, request: AddressRequest) -> dict[str, Any]:
        """
        Parses address using multiple candidates and dynamic reranking weights.
        使用多个候选者和动态重排权重解析地址。
        """
        # Load weights from specific model version or active version
        # 从特定模型版本或活动版本加载权重
        dynamic_weights = RerankerArtifactLoader.load_weights(
            ADDRESSFORGE_WORKSPACE_NAME, 
            version=request.reranker_version
        )
        
        # Merge static policy weights with dynamic training weights
        # 将静态策略权重与动态训练权重合并
        effective_weights = self._parser_weights()
        effective_weights.update(dynamic_weights)

        candidates = _parser_candidates(
            request,
            default_profile=self._default_profile,
            default_parsers=self._default_parsers,
            parser_weights=effective_weights,
        )
        best = candidates[0] if candidates else None

        return {
            "profile": request.profile or self._default_profile,
            "parser_count": len(candidates),
            "candidates": [
                {
                    "parser_name": item.parser_name,
                    "parser_version": item.parser_version,
                    "score": item.score,
                    "match_rules": item.match_rules,
                    "parsed": item.parsed,
                    "street_number": item.parsed.get("street_number"),
                    "street_name": item.parsed.get("street_name"),
                    "unit_number": canonicalize_unit_number(item.parsed.get("unit_number")),
                    "city": item.parsed.get("city"),
                    "province": item.parsed.get("province"),
                    "postal_code": item.parsed.get("postal_code"),
                }
                for item in candidates
            ],
            "best_candidate": None
            if best is None
            else {
                "parser_name": best.parser_name,
                "parser_version": best.parser_version,
                "score": best.score,
                "match_rules": best.match_rules,
                "parsed": best.parsed,
                "street_number": best.parsed.get("street_number"),
                "street_name": best.parsed.get("street_name"),
                "unit_number": canonicalize_unit_number(best.parsed.get("unit_number")),
                "city": best.parsed.get("city"),
                "province": best.parsed.get("province"),
                "postal_code": best.parsed.get("postal_code"),
            },
            "input": {
                "raw_address_text": request.raw_address_text,
                "city": request.city,
                "province": request.province,
                "postal_code": request.postal_code,
                "country_code": request.country_code,
                "profile": request.profile or self._default_profile,
            },
        }

    def validate(self, request: AddressRequest) -> dict[str, Any]:
        profile = get_profile(request.profile or self._default_profile or request.country_code or "CA")
        parsed_result = self.parse(request)
        candidates = parsed_result.get("candidates") or []
        best = parsed_result["best_candidate"] or {}
        parsed = best.get("parsed") or {}
        normalized_city = normalize_city(parsed.get("city") or request.city)
        normalized_province = normalize_province(parsed.get("province") or request.province, profile)
        normalized_unit = canonicalize_unit_number(parsed.get("unit_number"))
        street_number = parsed.get("street_number")
        street_name = normalize_street_name(parsed.get("street_name"))
        postal_code = parsed.get("postal_code") or request.postal_code
        reference = None
        ref_score = 0.0
        if street_number and street_name and normalized_province:
            try:
                match = self._reference_matcher.match(
                    street_number,
                    street_name,
                    normalized_province,
                    normalized_city,
                    normalized_city,
                    None,
                    request.latitude,
                    request.longitude,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Reference match failed in public API: %s", exc)
                match = None
            if match:
                reference = dict(match.reference)
                reference.update(
                    {
                        "reference_confidence": match.score,
                        "reference_unit_count_hint": match.unit_count_hint,
                        "reference_unit_numbers": list(match.unit_numbers),
                        "reference_candidate_count": match.candidate_count,
                    }
                )
                ref_score = float(match.score)

        building_type = infer_structure_type(
            raw_address_text=request.raw_address_text,
            parsed_unit_number=normalized_unit,
            reference_unit_count_hint=int(reference.get("reference_unit_count_hint") or 0) if reference else None,
            reference_payload=reference,
        )

        parse_score = float(best.get("score") or 0.0)
        close_candidate_delta = self._policy_float("close_candidate_delta", 0.08)
        close_candidates = [
            item for item in candidates if float(item.get("score") or 0.0) >= max(parse_score - close_candidate_delta, 0.0)
        ]
        close_unit_candidates = [
            item
            for item in close_candidates
            if canonicalize_unit_number(item.get("unit_number"))
            and canonicalize_unit_number(item.get("unit_number")) != normalized_unit
        ]
        parser_disagreement = False
        if len(close_candidates) >= 2:
            normalized_pairs = {
                (
                    str(item.get("street_number") or "").strip(),
                    normalize_street_name(item.get("street_name")) or "",
                    canonicalize_unit_number(item.get("unit_number")) or "",
                )
                for item in close_candidates
            }
            parser_disagreement = len(normalized_pairs) >= 2

        if not street_number or not street_name:
            decision = "review"
            reason = "Address is incomplete and needs manual confirmation."
        elif reference and normalized_unit:
            decision = "accept"
            reason = "Reference matched and unit is present."
        elif reference and building_type == "multi_unit":
            decision = "enrich"
            reason = "Reference matched a multi-unit building; unit may be missing."
        elif reference and building_type == "commercial" and not normalized_unit:
            decision = "review"
            reason = "Reference matched a commercial address; suite or unit details may be missing."
        elif reference:
            decision = "accept"
            reason = "Reference matched a single-unit building."
        elif building_type == "commercial" and normalized_unit and parse_score >= self._policy_float("commercial_accept_threshold", 0.88):
            decision = "accept"
            reason = "Commercial address includes a strong suite or room identifier."
        elif building_type == "multi_unit" and normalized_unit and parse_score >= self._policy_float("multi_unit_accept_threshold", 0.72):
            decision = "accept"
            reason = "Multi-unit address includes a parsed unit with sufficient parser confidence."
        elif not normalized_unit and close_unit_candidates and building_type in {"multi_unit", "commercial"}:
            decision = "enrich"
            reason = "Another strong parser candidate found a likely unit."
        elif parser_disagreement and parse_score >= self._policy_float("parser_disagreement_review_threshold", 0.72):
            decision = "review"
            reason = "Strong parser candidates disagree on the structured address."
        elif building_type == "commercial" and parse_score >= self._policy_float("commercial_review_threshold", 0.72):
            decision = "review"
            reason = "Commercial-looking address parsed well, but unit details may need confirmation."
        elif parse_score >= self._policy_float("high_confidence_accept_threshold", 0.82):
            decision = "accept"
            reason = "Parser confidence is high enough without reference confirmation."
        elif parse_score >= self._policy_float("moderate_confidence_review_threshold", 0.62):
            decision = "review"
            reason = "Parser confidence is moderate; review is safer."
        else:
            decision = "reject"
            reason = "Parser confidence is too low."

        if reference and request.latitude is not None and request.longitude is not None and ref_score < self._policy_float("gps_weak_match_threshold", 0.62):
            reason = f"{reason} GPS weakly matches the external reference."

        confidence = max(parse_score, ref_score)
        canonical_base_key = (
            build_base_address_key(street_number, street_name, normalized_city, normalized_province, postal_code)
            if street_number and street_name and normalized_province
            else None
        )
        canonical_full_key = build_full_address_key(canonical_base_key, normalized_unit) if canonical_base_key else None
        suggested_unit = normalized_unit
        if not suggested_unit and reference and reference.get("reference_unit_numbers"):
            suggested_unit = reference["reference_unit_numbers"][0]
        if not suggested_unit and close_unit_candidates:
            suggested_unit = canonicalize_unit_number(close_unit_candidates[0].get("unit_number"))
        return {
            "profile": request.profile or self._default_profile,
            "decision": decision,
            "confidence": round(confidence, 4),
            "reason": reason,
            "building_type": building_type,
            "suggested_unit_number": suggested_unit,
            "canonical": {
                "base_address_key": canonical_base_key,
                "full_address_key": canonical_full_key,
                "street_number": street_number,
                "street_name": street_name,
                "unit_number": normalized_unit,
                "city": normalized_city,
                "province": normalized_province,
                "postal_code": postal_code,
                "country_code": request.country_code or "CA",
            },
            "parser_result": parsed_result,
            "reference": reference,
            "hints": {
                "gps_conflict": bool(
                    reference
                    and request.latitude is not None
                    and request.longitude is not None
                    and ref_score < self._policy_float("gps_conflict_threshold", 0.5)
                ),
                "reference_available": bool(reference),
                "reference_score": round(ref_score, 4),
                "parser_disagreement": parser_disagreement,
                "alternate_unit_candidates": [
                    canonicalize_unit_number(item.get("unit_number"))
                    for item in close_unit_candidates
                    if canonicalize_unit_number(item.get("unit_number"))
                ][:3],
            },
        }

    def explain(self, request: ExplainRequest) -> dict[str, Any]:
        validation = self.validate(request)
        steps = [
            f"Profile: {validation['profile']}",
            f"Decision: {validation['decision']}",
            f"Confidence: {validation['confidence']}",
            f"Building type: {validation['building_type']}",
        ]
        if validation.get("suggested_unit_number"):
            steps.append(f"Suggested unit: {validation['suggested_unit_number']}")
        if validation.get("reference"):
            ref = validation["reference"]
            steps.append(
                f"Reference: {ref.get('source_name')} {ref.get('external_id')} (score={ref.get('reference_confidence')})"
            )
        if validation.get("canonical", {}).get("base_address_key"):
            steps.append(f"Canonical key: {validation['canonical']['base_address_key']}")
        return {
            "summary": validation["reason"],
            "steps": steps if request.include_steps else [],
            "validation": validation,
        }


service = AddressPlatformService()
app = FastAPI(title=APP_TITLE, version=PLATFORM_VERSION)


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "name": APP_TITLE,
        "platform_version": PLATFORM_VERSION,
        "api_version": API_VERSION,
        "default_model_profile": DEFAULT_MODEL_PROFILE,
        "endpoints": [
            "/health",
            "/api/v1/model",
            "/api/v1/models",
            "/api/v1/workspaces",
            "/api/v1/gold/labels",
            "/api/v1/gold/snapshots",
            "/api/v1/gold/freeze",
            "/api/v1/active-learning/queue",
            "/api/v1/active-learning/seed",
            "/api/v1/normalize",
            "/api/v1/parse",
            "/api/v1/validate",
            "/api/v1/explain",
        ],
    }


@app.get("/api/v1/model")
async def model_info() -> dict[str, Any]:
    return service.model_info()


@app.get("/api/v1/models")
async def models(workspace_name: str | None = None) -> dict[str, Any]:
    target_workspace = workspace_name or ADDRESSFORGE_WORKSPACE_NAME
    try:
        snapshot = bootstrap_default_registry()
        ws_name = snapshot["workspace"].get("workspace_name", target_workspace)
        if workspace_name and workspace_name != ws_name:
            ws_name = workspace_name
        models_list = list_models(ws_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Model list registry unavailable: %s", exc)
        ws_name = target_workspace
        models_list = []
    return {
        "workspace_name": ws_name,
        "models": models_list,
    }


@app.get("/api/v1/workspaces")
async def workspaces() -> dict[str, Any]:
    snapshot = bootstrap_default_registry()
    return {
        "workspaces": list_workspaces(),
        "default_workspace": snapshot["workspace"],
        "active_model": snapshot["model"],
    }


@app.get("/api/v1/gold/labels")
async def gold_labels(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    review_status: str | None = None,
    label_source: str | None = None,
    task_type: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    return {
        "workspace_name": workspace_name,
        "total_accepted_human": count_gold_labels(workspace_name, review_status="accepted", label_source="human"),
        "labels": list_gold_labels(
            workspace_name=workspace_name,
            review_status=review_status,
            label_source=label_source,
            task_type=task_type,
            limit=limit,
        ),
    }


@app.get("/api/v1/gold/snapshots")
async def gold_snapshots(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    label_source_filter: str | None = None,
    task_type: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    return {
        "workspace_name": workspace_name,
        "snapshots": list_gold_snapshots(
            workspace_name=workspace_name,
            label_source_filter=label_source_filter,
            task_type=task_type,
            limit=limit,
        ),
    }


@app.get("/api/v1/active-learning/queue")
async def active_learning_queue(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    status: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    return {
        "workspace_name": workspace_name,
        "queued_total": count_active_learning_queue(workspace_name, status="queued"),
        "items": list_active_learning_queue(workspace_name=workspace_name, status=status, limit=limit),
    }


@app.post("/api/v1/normalize")
async def normalize(request: AddressRequest) -> dict[str, Any]:
    return service.normalize(request)


@app.post("/api/v1/parse")
async def parse(request: AddressRequest) -> dict[str, Any]:
    return service.parse(request)


@app.post("/api/v1/validate")
async def validate(request: AddressRequest) -> dict[str, Any]:
    return service.validate(request)


@app.post("/api/v1/explain")
async def explain(request: ExplainRequest) -> dict[str, Any]:
    return service.explain(request)


@app.post("/api/v1/gold/labels")
async def upsert_gold(request: GoldLabelRequest) -> dict[str, Any]:
    label = upsert_gold_label(
        workspace_name=request.workspace_name,
        source_name=request.source_name,
        source_id=request.source_id,
        task_type=request.task_type,
        label_json=request.label_json,
        review_status=request.review_status,
        label_source=request.label_source,
        score=request.score,
        notes=request.notes,
    )
    return {"status": "ok", "label": label}


@app.post("/api/v1/gold/freeze")
async def freeze_gold(request: GoldFreezeRequest) -> dict[str, Any]:
    result = freeze_gold_set(
        workspace_name=request.workspace_name,
        gold_set_version=request.gold_set_version,
        split_version=request.split_version,
        label_source_filter=request.label_source_filter,
        task_type=request.task_type,
        notes=request.notes,
    )
    return {"status": "ok", "result": result}


@app.post("/api/v1/active-learning/seed")
async def seed_active_learning(request: ActiveLearningSeedRequest) -> dict[str, Any]:
    result = seed_active_learning_queue(
        workspace_name=request.workspace_name,
        limit=request.limit,
        confidence_threshold=request.confidence_threshold,
    )
    return {"status": "ok", "result": result}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("ADDRESSFORGE_PORT", os.getenv("ADDRESS_PLATFORM_PORT", "8010")))
    uvicorn.run("addressforge.api.server:app", host="127.0.0.1", port=port, reload=False)
