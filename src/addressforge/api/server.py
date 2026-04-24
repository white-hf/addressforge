from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from addressforge.core.common import (
    build_base_address_key,
    build_full_address_key,
    canonicalize_unit_number,
    hybrid_canadian_parse_address,
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
from addressforge.models import bootstrap_default_registry, get_active_model, list_models


APP_TITLE = "Address Platform API / 地址平台 API"
API_VERSION = "v1"
DEFAULT_MODEL_PROFILE = os.getenv("ADDRESS_PLATFORM_DEFAULT_PROFILE", "base_canada")
PLATFORM_VERSION = os.getenv("ADDRESS_PLATFORM_VERSION", "AddressForge.0.0")
MODEL_VERSION = os.getenv("ADDRESS_PLATFORM_MODEL_VERSION", "canada_default_v1")
REFERENCE_VERSION = os.getenv("ADDRESS_PLATFORM_REFERENCE_VERSION", "geonova_current")
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


class ExplainRequest(AddressRequest):
    include_steps: bool = True


@dataclass(frozen=True)
class CandidateView:
    parser_name: str
    parser_version: str
    score: float
    parsed: dict[str, Any]
    match_rules: list[str]


def _score_candidate(parsed: dict[str, Any]) -> float:
    parse_confidence = float(parsed.get("parse_confidence") or 0.0)
    unit_confidence = float(parsed.get("unit_confidence") or 0.0)
    postal_confidence = float(parsed.get("postal_confidence") or 0.0)
    base_score = 0.70 * parse_confidence + 0.20 * unit_confidence + 0.10 * postal_confidence
    if parsed.get("street_number") and parsed.get("street_name"):
        base_score += 0.05
    if parsed.get("postal_code"):
        base_score += 0.03
    return round(min(base_score, 0.99), 4)


def _parser_candidates(request: AddressRequest) -> list[CandidateView]:
    raw_text = normalize_space(request.raw_address_text)
    parser_names = tuple(request.parsers or DEFAULT_PARSERS)
    candidates: list[CandidateView] = []
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
        parsed = parser_fn(
            raw_text,
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
        parsed.setdefault("province", normalize_province(request.province))
        parsed.setdefault("postal_code", request.postal_code)
        score = _score_candidate(parsed)
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
    def __init__(self) -> None:
        self._reference_matcher = GeoNovaReferenceMatcher()

    def model_info(self) -> dict[str, Any]:
        reference_count = 0
        try:
            from addressforge.core.common import fetch_all

            rows = fetch_all(
                "SELECT COUNT(*) AS cnt FROM external_building_reference WHERE is_active = 1"
            )
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
            "default_model_profile": DEFAULT_MODEL_PROFILE,
            "workspace_name": workspace_name,
            "supported_profiles": list(SUPPORTED_PROFILES),
            "default_parsers": list(DEFAULT_PARSERS),
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
            ],
            "open_source": True,
            "self_hosted": True,
        }

    def normalize(self, request: AddressRequest) -> dict[str, Any]:
        raw_text = normalize_space(request.raw_address_text)
        parsed = simple_parse_address(
            raw_text,
            fallback_postal=request.postal_code,
            fallback_city=request.city,
            fallback_province=request.province,
        )
        normalized_city = normalize_city(request.city) or parsed["city"]
        normalized_province = normalize_province(request.province) or parsed["province"]
        result = {
            "profile": request.profile or DEFAULT_MODEL_PROFILE,
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
        candidates = _parser_candidates(request)
        best = candidates[0] if candidates else None
        return {
            "profile": request.profile or DEFAULT_MODEL_PROFILE,
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
                "profile": request.profile or DEFAULT_MODEL_PROFILE,
            },
        }

    def validate(self, request: AddressRequest) -> dict[str, Any]:
        parsed_result = self.parse(request)
        best = parsed_result["best_candidate"] or {}
        parsed = best.get("parsed") or {}
        normalized_city = normalize_city(parsed.get("city") or request.city)
        normalized_province = normalize_province(parsed.get("province") or request.province)
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

        building_type = "unknown"
        if reference:
            if int(reference.get("reference_unit_count_hint") or 0) >= 2:
                building_type = "multi_unit"
            elif int(reference.get("reference_unit_count_hint") or 0) == 1:
                building_type = "single_unit"
        elif normalized_unit:
            building_type = "multi_unit"

        parse_score = float(best.get("score") or 0.0)
        if not street_number or not street_name:
            decision = "review"
            reason = "Address is incomplete and needs manual confirmation."
        elif reference and normalized_unit:
            decision = "accept"
            reason = "Reference matched and unit is present."
        elif reference and int(reference.get("reference_unit_count_hint") or 0) >= 2:
            decision = "enrich"
            reason = "Reference matched a multi-unit building; unit may be missing."
        elif reference:
            decision = "accept"
            reason = "Reference matched a single-unit building."
        elif parse_score >= 0.82:
            decision = "accept"
            reason = "Parser confidence is high enough without reference confirmation."
        elif parse_score >= 0.62:
            decision = "review"
            reason = "Parser confidence is moderate; review is safer."
        else:
            decision = "reject"
            reason = "Parser confidence is too low."

        if reference and request.latitude is not None and request.longitude is not None and ref_score < 0.62:
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
        return {
            "profile": request.profile or DEFAULT_MODEL_PROFILE,
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
                "gps_conflict": bool(reference and request.latitude is not None and request.longitude is not None and ref_score < 0.5),
                "reference_available": bool(reference),
                "reference_score": round(ref_score, 4),
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


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("ADDRESS_PLATFORM_PORT", "8010"))
    uvicorn.run("addressforge.api.server:app", host="127.0.0.1", port=port, reload=False)
