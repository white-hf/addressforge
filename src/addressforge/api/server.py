from __future__ import annotations

import json
import os
import re
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
    has_numbered_road_signal,
    hybrid_canadian_parse_address,
    infer_structure_type,
    looks_like_bare_trailing_unit_city_pattern,
    libpostal_parse_address,
    normalize_city,
    normalize_province,
    normalize_space,
    normalize_street_name,
    normalize_unit_signal_text,
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
from addressforge.services.model_service import get_model_service
from addressforge.services.model_service import ModelService
from addressforge.services.reranker_service import get_reranker_service
from addressforge.core.retrieval import get_vector_engine


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


def _ensure_candidate_feature_vector(parsed: dict[str, Any], raw_text: str) -> dict[str, Any]:
    feature_vector = parsed.get("feature_vector")
    if not isinstance(feature_vector, dict):
        feature_vector = {}
    normalized_raw_text = normalize_unit_signal_text(raw_text).upper()
    normalized_street_name = normalize_street_name(parsed.get("street_name")) or ""
    feature_vector.setdefault("pattern", parsed.get("unit_source"))
    feature_vector.setdefault("unit_present", bool(canonicalize_unit_number(parsed.get("unit_number"))))
    feature_vector.setdefault(
        "has_explicit_unit_hint",
        bool(re.search(r"\b(?:SUITE|STE|UNIT|APT|APARTMENT|ROOM|RM|FLOOR|FL|#)\b", normalized_raw_text)),
    )
    feature_vector.setdefault(
        "has_residential_unit_hint",
        bool(re.search(r"\b(?:BASEMENT|LOWER|UPPER|REAR|FRONT|SIDE|PENTHOUSE|PH|MAIN FLOOR|GROUND FLOOR|GF)\b", normalized_raw_text)),
    )
    feature_vector.setdefault(
        "has_geographic_modifier_only",
        bool(
            re.search(r"\b(?:UPPER|LOWER)\s+[A-Z][A-Z' -]{2,}\b", normalized_raw_text)
            and not re.search(r"\b(?:APT|UNIT|SUITE|STE|ROOM|RM|#)\b", normalized_raw_text)
        ),
    )
    feature_vector.setdefault(
        "has_commercial_unit_hint",
        bool(re.search(r"\b(?:KIOSK|OFFICE|MALL|PLAZA|SQUARE|CENTRE|CENTER|SHOPPING)\b", normalized_raw_text)),
    )
    normalized_without_postal = re.sub(r"\b[A-Z]\d[A-Z]\s*\d[A-Z]\d\b", " ", normalized_raw_text)
    feature_vector.setdefault(
        "has_double_number_pattern",
        bool(
            re.search(
                r"^\s*\d+[A-Z]?\s+.+(?:,|\s)\s*\d+[A-Z]?\s+[A-Z][A-Z .'-]+\s+(?:NS|NB|ON|QC|PE|NL|MB|SK|AB|BC|YT|NT|NU)\b",
                normalized_without_postal,
            )
        ),
    )
    feature_vector.setdefault(
        "is_numbered_road_name",
        bool(
            has_numbered_road_signal(normalized_street_name)
            or has_numbered_road_signal(normalized_raw_text)
        ),
    )
    feature_vector.setdefault(
        "has_bare_trailing_unit_city_pattern",
        bool(
            looks_like_bare_trailing_unit_city_pattern(
                normalized_raw_text,
                street_number=parsed.get("street_number"),
                street_name=normalized_street_name,
                unit_number=parsed.get("unit_number"),
                city=parsed.get("city"),
                province=parsed.get("province"),
            )
        ),
    )
    feature_vector.setdefault("is_commercial", bool(feature_vector.get("has_commercial_unit_hint")))
    feature_vector.setdefault("regex_hit", int(bool(feature_vector.get("has_explicit_unit_hint"))))
    parsed["feature_vector"] = feature_vector
    return feature_vector


def _recover_candidate_unit_from_text(
    raw_text: str,
    parsed: dict[str, Any],
    *,
    fallback_city: str | None,
    fallback_province: str | None,
) -> None:
    if canonicalize_unit_number(parsed.get("unit_number")):
        return
    street_number = str(parsed.get("street_number") or "").strip()
    street_name = normalize_street_name(parsed.get("street_name"))
    if not street_number or not street_name:
        return
    normalized_raw_text = normalize_unit_signal_text(raw_text).upper()
    normalized_city = normalize_city(parsed.get("city") or fallback_city)
    normalized_province = normalize_province(parsed.get("province") or fallback_province, get_profile("CA"))
    recovered_unit = None
    residential_prefix_match = re.match(
        r"^\s*(BASEMENT|LOWER|UPPER|REAR|FRONT|SIDE|PENTHOUSE(?:\s+\d+)?|PH(?:\s+[A-Z0-9-]+)?|GF|GROUND FLOOR|MAIN FLOOR|MAIN FLR)\s+\d+[A-Z]?\s+",
        normalized_raw_text,
    )
    if residential_prefix_match:
        recovered_unit = canonicalize_unit_number(residential_prefix_match.group(1))
    explicit_unit_match = re.search(
        r"(?:\b(?:SUITE|STE|UNIT|APT|APARTMENT|ROOM|RM|FLOOR|FL)\b\s*([A-Z0-9-]+)|#\s*([A-Z0-9-]+))\b",
        normalized_raw_text,
    )
    if not recovered_unit and explicit_unit_match:
        recovered_unit = canonicalize_unit_number(explicit_unit_match.group(1) or explicit_unit_match.group(2))
    if not recovered_unit and normalized_city and normalized_province:
        trailing_bare_unit_match = re.search(
            rf",\s*(\d{{1,5}}[A-Z]?)\s*,?\s*{re.escape(normalized_city.upper())}\s*,?\s*{re.escape(normalized_province.upper())}\b",
            normalized_raw_text,
        )
        if trailing_bare_unit_match:
            recovered_unit = canonicalize_unit_number(trailing_bare_unit_match.group(1))
    if not recovered_unit and normalized_city and normalized_province:
        no_comma_bare_unit_match = re.search(
            rf"^\s*{re.escape(street_number)}\s+.+\s+(\d{{1,5}}[A-Z]?)\s+{re.escape(normalized_city.upper())}\s+{re.escape(normalized_province.upper())}(?:\b.*)?$",
            normalized_raw_text,
        )
        if no_comma_bare_unit_match:
            candidate_unit = canonicalize_unit_number(no_comma_bare_unit_match.group(1))
            if looks_like_bare_trailing_unit_city_pattern(
                normalized_raw_text,
                street_number=street_number,
                street_name=street_name,
                unit_number=candidate_unit,
                city=normalized_city,
                province=normalized_province,
            ):
                recovered_unit = candidate_unit
    if not recovered_unit and normalized_city:
        trailing_bare_unit_city_only_match = re.search(
            rf",\s*(\d{{1,5}}[A-Z]?)\s*,?\s*{re.escape(normalized_city.upper())}\b(?:\s*,?\s*{re.escape((normalized_province or '').upper())})?$",
            normalized_raw_text,
        )
        if trailing_bare_unit_city_only_match:
            recovered_unit = canonicalize_unit_number(trailing_bare_unit_city_only_match.group(1))
    if recovered_unit:
        parsed["unit_number"] = recovered_unit
        if not parsed.get("unit_source"):
            parsed["unit_source"] = "candidate_text_fallback"


def _score_candidate(
    parsed: dict[str, Any],
    *,
    raw_text: str | None = None,
    parser_name: str | None = None,
    parser_weights: dict[str, Any] | None = None,
    match_rule_weights: dict[str, Any] | None = None,
    candidate_feature_weights: dict[str, Any] | None = None,
    candidate_pair_weights: dict[str, Any] | None = None,
) -> float:
    parse_confidence = float(parsed.get("parse_confidence") or 0.0)
    unit_confidence = float(parsed.get("unit_confidence") or 0.0)
    postal_confidence = float(parsed.get("postal_confidence") or 0.0)
    base_score = 0.70 * parse_confidence + 0.20 * unit_confidence + 0.10 * postal_confidence
    normalized_raw_text = normalize_unit_signal_text(raw_text).upper() if raw_text else ""
    normalized_street_name = normalize_street_name(parsed.get("street_name"))
    if (
        parser_name == "libpostal"
        and str(parsed.get("street_number") or "").strip() == "123"
        and normalized_street_name == "MAIN ST"
        and not parsed.get("city")
        and not parsed.get("province")
        and "MAIN ST" not in normalized_raw_text
    ):
        # Suppress placeholder libpostal fallbacks that otherwise outrank real local parsers.
        base_score -= 0.45
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
    if isinstance(match_rule_weights, dict):
        feature_vector = parsed.get("feature_vector") or {}
        rule_keys = []
        pattern = feature_vector.get("pattern")
        if pattern:
            rule_keys.append(str(pattern))
        unit_source = parsed.get("unit_source")
        if unit_source:
            rule_keys.append(str(unit_source))
        if parsed.get("unit_number"):
            unit_bonus = match_rule_weights.get("__unit_present__")
            try:
                if unit_bonus is not None:
                    base_score += (float(unit_bonus) - 0.5) * 0.08
            except (TypeError, ValueError):
                pass
        if feature_vector.get("has_explicit_unit_hint"):
            unit_keyword_weight = match_rule_weights.get("__unit_keyword_present__")
            try:
                if unit_keyword_weight is not None:
                    adjustment = (float(unit_keyword_weight) - 0.5) * 0.06
                    base_score += adjustment if parsed.get("unit_number") else adjustment * -0.5
            except (TypeError, ValueError):
                pass
        if feature_vector.get("has_residential_unit_hint"):
            residential_hint_weight = match_rule_weights.get("__residential_unit_hint__")
            try:
                if residential_hint_weight is not None:
                    adjustment = (float(residential_hint_weight) - 0.5) * 0.06
                    if feature_vector.get("has_geographic_modifier_only") and not parsed.get("unit_number"):
                        base_score += adjustment * -0.6
                    else:
                        base_score += adjustment if parsed.get("unit_number") else adjustment * -0.4
            except (TypeError, ValueError):
                pass
        if feature_vector.get("has_commercial_unit_hint") or feature_vector.get("is_commercial"):
            commercial_hint_weight = match_rule_weights.get("__commercial_hint__")
            try:
                if commercial_hint_weight is not None:
                    base_score += (float(commercial_hint_weight) - 0.5) * 0.04
            except (TypeError, ValueError):
                pass
        seen: set[str] = set()
        for rule_key in rule_keys:
            if rule_key in seen:
                continue
            seen.add(rule_key)
            try:
                weight = match_rule_weights.get(rule_key)
                if weight is not None:
                    base_score += (float(weight) - 0.5) * 0.08
            except (TypeError, ValueError):
                continue
    if isinstance(candidate_feature_weights, dict):
        feature_vector = parsed.get("feature_vector") or {}
        candidate_unit = canonicalize_unit_number(parsed.get("unit_number"))
        unit_text_aligned = bool(
            candidate_unit
            and normalized_raw_text
            and (
                re.search(
                    rf"\b(?:SUITE|STE|UNIT|APT|APARTMENT|ROOM|RM|FLOOR|FL|#)\s*{re.escape(candidate_unit)}\b",
                    normalized_raw_text,
                )
                or re.search(rf"\b{re.escape(candidate_unit)}\b", normalized_raw_text)
            )
        )
        candidate_feature_keys: list[tuple[str, bool]] = [
            ("__candidate_complete_street__", bool(parsed.get("street_number") and parsed.get("street_name"))),
            ("__candidate_has_unit__", bool(parsed.get("unit_number"))),
            (
                "__candidate_street_text_alignment__",
                bool(normalized_street_name and normalized_raw_text and normalized_street_name.upper() in normalized_raw_text),
            ),
            (
                "__candidate_unit_with_hint__",
                bool(parsed.get("unit_number"))
                and bool(feature_vector.get("has_explicit_unit_hint") or feature_vector.get("has_residential_unit_hint")),
            ),
            (
                "__candidate_missing_unit_with_hint__",
                not bool(parsed.get("unit_number"))
                and bool(feature_vector.get("has_explicit_unit_hint") or feature_vector.get("has_residential_unit_hint")),
            ),
            (
                "__candidate_residential_alignment__",
                bool(feature_vector.get("has_residential_unit_hint") and not feature_vector.get("has_geographic_modifier_only")),
            ),
            ("__candidate_geographic_modifier_only__", bool(feature_vector.get("has_geographic_modifier_only"))),
            (
                "__candidate_bare_number_without_unit_hint__",
                bool(
                    parsed.get("unit_number")
                    and feature_vector.get("has_double_number_pattern")
                    and not feature_vector.get("has_explicit_unit_hint")
                    and not feature_vector.get("has_bare_trailing_unit_city_pattern")
                ),
            ),
            (
                "__candidate_bare_trailing_unit_city__",
                bool(parsed.get("unit_number") and feature_vector.get("has_bare_trailing_unit_city_pattern")),
            ),
            ("__candidate_numbered_road_name__", bool(feature_vector.get("is_numbered_road_name"))),
            (
                "__candidate_commercial_alignment__",
                bool(feature_vector.get("has_commercial_unit_hint") or feature_vector.get("is_commercial")),
            ),
            ("__candidate_unit_text_alignment__", unit_text_aligned),
        ]
        for feature_key, enabled in candidate_feature_keys:
            weight = candidate_feature_weights.get(feature_key)
            if weight is None:
                continue
            try:
                adjustment = (float(weight) - 0.5) * 0.08
            except (TypeError, ValueError):
                continue
            if enabled and feature_key in {
                "__candidate_geographic_modifier_only__",
                "__candidate_bare_number_without_unit_hint__",
                "__candidate_numbered_road_name__",
            }:
                base_score -= max(adjustment, 0.0) * 0.8
                continue
            if enabled:
                base_score += adjustment
            elif feature_key == "__candidate_missing_unit_with_hint__":
                base_score -= max(adjustment, 0.0) * 0.6
            elif feature_key in {"__candidate_geographic_modifier_only__", "__candidate_bare_number_without_unit_hint__", "__candidate_numbered_road_name__"}:
                base_score -= max(adjustment, 0.0) * 0.5
    if isinstance(candidate_pair_weights, dict):
        feature_vector = parsed.get("feature_vector") or {}
        candidate_unit = canonicalize_unit_number(parsed.get("unit_number"))
        normalized_raw_text = normalize_unit_signal_text(raw_text).upper() if raw_text else ""
        pair_features: list[tuple[str, bool]] = [
            ("__prefer_unit_candidate__", bool(candidate_unit)),
            (
                "__prefer_text_aligned_unit__",
                bool(candidate_unit and normalized_raw_text and re.search(rf"\b{re.escape(candidate_unit)}\b", normalized_raw_text)),
            ),
            (
                "__prefer_complete_street_candidate__",
                bool(parsed.get("street_number") and parsed.get("street_name")),
            ),
            (
                "__prefer_residential_unit_candidate__",
                bool(candidate_unit and feature_vector.get("has_residential_unit_hint") and not feature_vector.get("has_geographic_modifier_only")),
            ),
            (
                "__penalize_missing_unit_candidate__",
                not bool(candidate_unit)
                and bool(feature_vector.get("has_explicit_unit_hint") or feature_vector.get("has_residential_unit_hint")),
            ),
            (
                "__penalize_geographic_modifier_candidate__",
                bool(feature_vector.get("has_geographic_modifier_only") and not candidate_unit),
            ),
            (
                "__penalize_bare_number_unit_candidate__",
                bool(
                    candidate_unit
                    and feature_vector.get("has_double_number_pattern")
                    and not feature_vector.get("has_explicit_unit_hint")
                    and not feature_vector.get("has_bare_trailing_unit_city_pattern")
                ),
            ),
            (
                "__prefer_bare_trailing_unit_city_candidate__",
                bool(candidate_unit and feature_vector.get("has_bare_trailing_unit_city_pattern")),
            ),
            (
                "__penalize_numbered_road_unit_candidate__",
                bool(candidate_unit and feature_vector.get("is_numbered_road_name")),
            ),
        ]
        for feature_key, enabled in pair_features:
            weight = candidate_pair_weights.get(feature_key)
            if weight is None:
                continue
            try:
                adjustment = (float(weight) - 0.5) * 0.1
            except (TypeError, ValueError):
                continue
            if enabled and feature_key in {
                "__penalize_missing_unit_candidate__",
                "__penalize_geographic_modifier_candidate__",
                "__penalize_bare_number_unit_candidate__",
                "__penalize_numbered_road_unit_candidate__",
            }:
                base_score -= max(adjustment, 0.0)
                continue
            if enabled:
                base_score += adjustment
            elif feature_key in {
                "__penalize_missing_unit_candidate__",
                "__penalize_geographic_modifier_candidate__",
                "__penalize_bare_number_unit_candidate__",
                "__penalize_numbered_road_unit_candidate__",
            }:
                base_score -= max(adjustment, 0.0) * 0.7
    return round(min(base_score, 0.99), 4)


class RerankerArtifactLoader:
    @staticmethod
    def _load_artifact(workspace_name: str, *, version: str | None = None) -> dict[str, Any]:
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
            return json.loads(artifact_file.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load reranker artifact from %s: %s", artifact_path, exc)
            return {}

    @staticmethod
    def load_decision_policy(workspace_name: str, *, version: str | None = None) -> dict[str, Any]:
        """
        Loads the entire decision policy artifact (weights and bonuses).
        加载整个决策策略产物 (权重和加成)。
        """
        artifact = RerankerArtifactLoader._load_artifact(workspace_name, version=version)
        if not isinstance(artifact, dict):
            return {}
        decision_policy = artifact.get("decision_policy")
        if isinstance(decision_policy, dict):
            return decision_policy
        if "parser_weights" in artifact or "match_rule_weights" in artifact:
            return artifact
        return {}

    @staticmethod
    def load_weights(workspace_name: str, *, version: str | None = None) -> dict[str, Any]:
        decision_policy = RerankerArtifactLoader.load_decision_policy(workspace_name, version=version)
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
    match_rule_weights: dict[str, Any] | None = None,
    candidate_feature_weights: dict[str, Any] | None = None,
    candidate_pair_weights: dict[str, Any] | None = None,
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
        _recover_candidate_unit_from_text(
            raw_text,
            parsed,
            fallback_city=request.city,
            fallback_province=request.province,
        )
        _ensure_candidate_feature_vector(parsed, raw_text)
        score = _score_candidate(
            parsed,
            raw_text=raw_text,
            parser_name=parser_name,
            parser_weights=parser_weights,
            match_rule_weights=match_rule_weights,
            candidate_feature_weights=candidate_feature_weights,
            candidate_pair_weights=candidate_pair_weights,
        )
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
        model_service: ModelService | None = None,
    ) -> None:
        self._reference_matcher = GeoNovaReferenceMatcher()
        self._default_profile = default_profile or DEFAULT_MODEL_PROFILE
        self._default_parsers = default_parsers or DEFAULT_PARSERS
        self._decision_policy = decision_policy or {}
        
        # New: ML Model Service for supervised decisioning
        # 新增：用于监督决策的 ML 模型服务
        self._model_service = model_service or get_model_service()
        self._reranker_service = get_reranker_service()
        self._vector_engine = get_vector_engine()

    def _policy_float(self, key: str, default: float) -> float:
        value = self._decision_policy.get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _parser_weights(self) -> dict[str, Any]:
        value = self._decision_policy.get("parser_weights") or {}
        return value if isinstance(value, dict) else {}

    def _match_rule_weights(self) -> dict[str, Any]:
        value = self._decision_policy.get("match_rule_weights") or {}
        return value if isinstance(value, dict) else {}

    def _candidate_feature_weights(self) -> dict[str, Any]:
        value = self._decision_policy.get("candidate_feature_weights") or {}
        return value if isinstance(value, dict) else {}

    def _candidate_pair_weights(self) -> dict[str, Any]:
        value = self._decision_policy.get("candidate_pair_weights") or {}
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
        dynamic_policy = RerankerArtifactLoader.load_decision_policy(
            ADDRESSFORGE_WORKSPACE_NAME, 
            version=request.reranker_version
        )
        dynamic_weights = dynamic_policy.get("parser_weights") if isinstance(dynamic_policy, dict) else {}
        dynamic_match_rule_weights = dynamic_policy.get("match_rule_weights") if isinstance(dynamic_policy, dict) else {}

        effective_weights = dict(self._parser_weights())
        if isinstance(dynamic_weights, dict):
            effective_weights.update(dynamic_weights)
        effective_match_rule_weights = dict(self._match_rule_weights())
        if isinstance(dynamic_match_rule_weights, dict):
            effective_match_rule_weights.update(dynamic_match_rule_weights)
        dynamic_candidate_feature_weights = dynamic_policy.get("candidate_feature_weights") if isinstance(dynamic_policy, dict) else {}
        effective_candidate_feature_weights = dict(self._candidate_feature_weights())
        if isinstance(dynamic_candidate_feature_weights, dict):
            effective_candidate_feature_weights.update(dynamic_candidate_feature_weights)
        dynamic_candidate_pair_weights = dynamic_policy.get("candidate_pair_weights") if isinstance(dynamic_policy, dict) else {}
        effective_candidate_pair_weights = dict(self._candidate_pair_weights())
        if isinstance(dynamic_candidate_pair_weights, dict):
            effective_candidate_pair_weights.update(dynamic_candidate_pair_weights)

        candidates = _parser_candidates(
            request,
            default_profile=self._default_profile,
            default_parsers=self._default_parsers,
            parser_weights=effective_weights,
            match_rule_weights=effective_match_rule_weights,
            candidate_feature_weights=effective_candidate_feature_weights,
            candidate_pair_weights=effective_candidate_pair_weights,
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
        
        # New: Phase 13 - Step 1: Building Anchor Retrieval (Vector Bedrock)
        # 新增：第 13 阶段 - 步骤 1：建筑锚点检索（向量基石）
        semantic_anchors = self._vector_engine.retrieve(request.raw_address_text, top_k=3)
        
        # Inject semantic anchors into request for parser guidance
        # 将语义锚点注入请求以指导解析器
        request_with_context = request
        if semantic_anchors:
            # We can use the top anchor to provide 'hints' to the existing parsers
            best_anchor = semantic_anchors[0]
            # If the user didn't provide city/province, use the anchor's
            if not request.city:
                request_with_context.city = best_anchor.get("city")
            if not request.province:
                request_with_context.province = best_anchor.get("province")

        parsed_result = self.parse(request_with_context)
        candidates = parsed_result.get("candidates") or []
        
        # New: Phase 10 - ML Candidate Reranking
        # 新增：第 10 阶段 - ML 候选人重排
        # Enhanced for Phase 13: Pass semantic anchors to reranker for 'Entity Alignment' score
        # 第 13 阶段增强：将语义锚点传递给重排器以获得“实体对齐”分数
        reranked_candidates = self._reranker_service.rerank_candidates(
            request.raw_address_text, 
            candidates,
            semantic_anchors=semantic_anchors
        )
        best = reranked_candidates[0] if reranked_candidates else {}
        
        parsed = best.get("parsed") or {}
        normalized_raw_text = normalize_unit_signal_text(request.raw_address_text)
        normalized_city = normalize_city(parsed.get("city") or request.city)
        normalized_province = normalize_province(parsed.get("province") or request.province, profile)
        normalized_unit = canonicalize_unit_number(parsed.get("unit_number"))
        if not normalized_unit:
            residential_prefix_match = re.match(
                r"^\s*(BASEMENT|LOWER|UPPER|REAR|FRONT|SIDE|PENTHOUSE(?:\s+\d+)?|PH(?:\s+[A-Z0-9-]+)?|GF|GROUND FLOOR|MAIN FLOOR|MAIN FLR)\s+\d+[A-Z]?\s+",
                normalized_raw_text.upper(),
            )
            if residential_prefix_match:
                normalized_unit = canonicalize_unit_number(residential_prefix_match.group(1))
        if not normalized_unit:
            explicit_unit_match = re.search(
                r"(?:\b(?:SUITE|STE|UNIT|APT|APARTMENT|ROOM|RM|FLOOR|FL)\b\s*([A-Z0-9-]+)|#\s*([A-Z0-9-]+))\b",
                normalized_raw_text,
            )
            if explicit_unit_match:
                normalized_unit = canonicalize_unit_number(explicit_unit_match.group(1) or explicit_unit_match.group(2))
        if not normalized_unit and normalized_city and normalized_province:
            trailing_bare_unit_match = re.search(
                rf",\s*(\d{{1,5}}[A-Z]?)\s*,?\s*{re.escape(normalized_city.upper())}\s*,?\s*{re.escape(normalized_province.upper())}\b",
                normalized_raw_text,
            )
            if trailing_bare_unit_match:
                normalized_unit = canonicalize_unit_number(trailing_bare_unit_match.group(1))
        if not normalized_unit and normalized_city:
            trailing_bare_unit_city_only_match = re.search(
                rf",\s*(\d{{1,5}}[A-Z]?)\s*,?\s*{re.escape(normalized_city.upper())}\b(?:\s*,?\s*{re.escape(normalized_province.upper())})?$",
                normalized_raw_text,
            )
            if trailing_bare_unit_city_only_match:
                normalized_unit = canonicalize_unit_number(trailing_bare_unit_city_only_match.group(1))
        street_number = parsed.get("street_number")
        street_name = normalize_street_name(parsed.get("street_name"))
        postal_code = parsed.get("postal_code") or request.postal_code
        reference = None
        ref_score = 0.0
        reference_gap_reason = None
        
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
            else:
                # Diagnose reference gap
                # 诊断参考差距
                reference_gap_reason = self._reference_matcher.diagnose_gap(
                    street_number,
                    street_name,
                    normalized_province,
                    city=normalized_city,
                    municipality=normalized_city,
                    county=None,
                    lat=request.latitude,
                    lon=request.longitude,
                )

        building_type = infer_structure_type(
            raw_address_text=request.raw_address_text,
            parsed_unit_number=normalized_unit,
            reference_unit_count_hint=int(reference.get("reference_unit_count_hint") or 0) if reference else None,
            reference_payload=reference,
            unit_source=best.get("parsed", {}).get("unit_source") if best else None,
        )

        parse_score = float(best.get("score") or 0.0)
        parsed_pattern = (
            str(best.get("parsed", {}).get("feature_vector", {}).get("pattern") or "").strip()
            if best
            else ""
        )
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
        elif (
            parser_disagreement
            and building_type == "single_unit"
            and not normalized_unit
            and not reference
            and not close_unit_candidates
            and parse_score >= self._policy_float("single_unit_disagreement_accept_threshold", 0.68)
        ):
            decision = "accept"
            reason = "Single-unit structure is complete enough to accept despite weaker parser disagreement."
        elif (
            building_type == "single_unit"
            and not normalized_unit
            and not reference
            and parsed_pattern in {
                "duplicate_number_before_known_city",
                "route_only_before_city",
                "reversed_civic_before_city",
                "prefixed_civic_before_city",
            }
            and parse_score >= self._policy_float("single_unit_pattern_accept_threshold", 0.72)
        ):
            decision = "accept"
            reason = "Single-unit structure matches a known recoverable review pattern."
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
            decision = "review"
            reason = "Parser confidence is low; review is safer than rejection."

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
            
        # Shadow ML Prediction for parallel evaluation
        # 影子 ML 预测，用于并行评估
        ml_result = self._model_service.predict_decision(
            request.raw_address_text,
            parsed,
            parser_name=best.get("parser_name", "hybrid"),
            validation_context={
                "confidence": confidence,
                "reason": reason,
                "hints": {
                    "reference_score": ref_score,
                    "gps_conflict": bool(ref_score < self._policy_float("gps_weak_match_threshold", 0.62)) if reference else False,
                    "parser_disagreement": parser_disagreement
                }
            },
            reference_context=reference,
            building_type=building_type,
            current_decision=decision,
        )
        ml_shadow_decision = str(ml_result.get("ml_decision") or "").strip().lower()
        shadow_agrees = bool(ml_shadow_decision) and ml_shadow_decision == decision
        if not ml_shadow_decision:
            disagreement_reason = "model_unavailable"
        elif shadow_agrees:
            disagreement_reason = "agree"
        elif decision == "accept" and ml_shadow_decision == "review":
            disagreement_reason = "model_more_conservative_review"
        elif decision == "review" and ml_shadow_decision == "accept":
            disagreement_reason = "model_more_aggressive_accept"
        elif ml_shadow_decision == "reject" and decision != "reject":
            disagreement_reason = "model_reject_escalation"
        elif decision == "reject" and ml_shadow_decision != "reject":
            disagreement_reason = "model_reject_recovery"
        else:
            disagreement_reason = "general_disagreement"

        return {
            "profile": request.profile or self._default_profile,
            "decision": decision,
            "confidence": round(confidence, 4),
            "reason": reason,
            "building_type": building_type,
            "suggested_unit_number": suggested_unit,
            "ml_decision": ml_result,
            "shadow_assist": {
                "heuristic_decision": decision,
                "model_decision": ml_shadow_decision or None,
                "agrees_with_heuristic": shadow_agrees,
                "disagreement_reason": disagreement_reason,
                "model_status": ml_result.get("status"),
                "model_score": ml_result.get("ml_score"),
            },
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
            "parser_result": {
                **parsed_result,
                "candidates": reranked_candidates,
                "best_candidate": best
            },
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
                "reference_gap_reason": reference_gap_reason,
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
        if validation.get("ml_decision"):
            ml = validation["ml_decision"]
            steps.append(f"ML Score (Shadow): {ml.get('ml_score')} -> {ml.get('ml_decision')}")
        if validation.get("shadow_assist"):
            shadow = validation["shadow_assist"]
            if not shadow.get("agrees_with_heuristic"):
                steps.append(
                    f"Shadow Disagreement: {shadow.get('heuristic_decision')} vs {shadow.get('model_decision')} ({shadow.get('disagreement_reason')})"
                )
        if validation.get("suggested_unit_number"):
            steps.append(f"Suggested unit: {validation['suggested_unit_number']}")
        if validation.get("reference"):
            ref = validation["reference"]
            steps.append(
                f"Reference: {ref.get('source_name')} {ref.get('external_id')} (score={ref.get('reference_confidence')})"
            )
        else:
            gap_reason = validation.get("hints", {}).get("reference_gap_reason")
            if gap_reason:
                steps.append(f"Reference Gap: {gap_reason}")
        
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
