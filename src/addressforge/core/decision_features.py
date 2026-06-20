from __future__ import annotations

from typing import Any

import pandas as pd

from addressforge.core.common import canonicalize_unit_number

DECISION_LABELS = ("accept", "review", "reject")

DECISION_CATEGORICAL_FEATURES = (
    "pattern",
    "unit_source",
    "decision_reason",
    "task_type",
    "sample_pool",
)

DECISION_NUMERIC_FEATURES = (
    "confidence",
    "reference_score",
    "reference_candidate_count",
    "reference_has_unit_hint",
    "gps_conflict",
    "parser_disagreement",
    "street_number_present",
    "street_name_present",
    "unit_present",
    "explicit_unit_hint",
    "residential_unit_hint",
    "commercial_unit_hint",
    "geographic_modifier_only",
    "double_number_pattern",
    "bare_trailing_unit_city_pattern",
    "numbered_road_name",
    "building_type_multi_unit",
    "building_type_commercial",
    "raw_text_length",
)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _reference_candidate_count(reference_json: dict[str, Any]) -> int:
    for key in ("candidates", "matches", "reference_candidates"):
        value = reference_json.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def _reference_has_unit_hint(reference_json: dict[str, Any]) -> int:
    candidates = reference_json.get("candidates")
    if not isinstance(candidates, list):
        candidates = reference_json.get("matches")
    if not isinstance(candidates, list):
        return 0
    for item in candidates:
        if not isinstance(item, dict):
            continue
        if canonicalize_unit_number(item.get("unit_number")):
            return 1
        if canonicalize_unit_number((item.get("canonical") or {}).get("unit_number")):
            return 1
    return 0


def build_decision_inference_feature_row(
    raw_text: str,
    parsed: dict[str, Any] | None,
    *,
    parser_name: str = "unknown",
    validation_context: dict[str, Any] | None = None,
    reference_context: dict[str, Any] | None = None,
    building_type: str | None = None,
    current_decision: str | None = None,
) -> dict[str, Any]:
    parsed = parsed if isinstance(parsed, dict) else {}
    validation_json = validation_context if isinstance(validation_context, dict) else {}
    reference_json = reference_context if isinstance(reference_context, dict) else {}
    hints = validation_json.get("hints") if isinstance(validation_json.get("hints"), dict) else {}
    feature_vector = parsed.get("feature_vector") if isinstance(parsed.get("feature_vector"), dict) else {}
    normalized_building_type = str(building_type or "").strip().lower()
    normalized_raw_text = str(raw_text or "")

    return {
        "label": "",
        "source_id": "",
        "raw_address_text": normalized_raw_text,
        "current_decision": str(current_decision or "").strip().lower(),
        "pattern": str(feature_vector.get("pattern") or parsed.get("unit_source") or "").strip().lower(),
        "unit_source": str(parsed.get("unit_source") or parser_name or "").strip().lower(),
        "decision_reason": str(validation_json.get("reason") or "").strip().lower(),
        "task_type": "runtime",
        "sample_pool": "",
        "confidence": safe_float(validation_json.get("confidence"), 0.0),
        "reference_score": safe_float(hints.get("reference_score"), 0.0),
        "reference_candidate_count": float(_reference_candidate_count(reference_json)),
        "reference_has_unit_hint": float(_reference_has_unit_hint(reference_json)),
        "gps_conflict": 1.0 if bool(hints.get("gps_conflict")) else 0.0,
        "parser_disagreement": 1.0 if bool(hints.get("parser_disagreement")) else 0.0,
        "street_number_present": 1.0 if str(parsed.get("street_number") or "").strip() else 0.0,
        "street_name_present": 1.0 if str(parsed.get("street_name") or "").strip() else 0.0,
        "unit_present": 1.0 if canonicalize_unit_number(parsed.get("unit_number")) else 0.0,
        "explicit_unit_hint": 1.0 if bool(feature_vector.get("has_explicit_unit_hint")) else 0.0,
        "residential_unit_hint": 1.0 if bool(feature_vector.get("has_residential_unit_hint")) else 0.0,
        "commercial_unit_hint": 1.0 if bool(feature_vector.get("has_commercial_unit_hint") or feature_vector.get("is_commercial")) else 0.0,
        "geographic_modifier_only": 1.0 if bool(feature_vector.get("has_geographic_modifier_only")) else 0.0,
        "double_number_pattern": 1.0 if bool(feature_vector.get("has_double_number_pattern")) else 0.0,
        "bare_trailing_unit_city_pattern": 1.0 if bool(feature_vector.get("has_bare_trailing_unit_city_pattern")) else 0.0,
        "numbered_road_name": 1.0 if bool(feature_vector.get("is_numbered_road_name")) else 0.0,
        "building_type_multi_unit": 1.0 if normalized_building_type == "multi_unit" else 0.0,
        "building_type_commercial": 1.0 if normalized_building_type == "commercial" else 0.0,
        "raw_text_length": float(len(normalized_raw_text.strip())),
    }


def rows_to_feature_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame_rows: list[dict[str, Any]] = []
    for row in rows:
        frame_row: dict[str, Any] = {}
        for feature_name in DECISION_NUMERIC_FEATURES:
            frame_row[feature_name] = safe_float(row.get(feature_name), 0.0)
        for feature_name in DECISION_CATEGORICAL_FEATURES:
            frame_row[feature_name] = str(row.get(feature_name) or "")
        frame_rows.append(frame_row)
    return pd.DataFrame(frame_rows)


def normalize_decision_feature_frame(
    frame: pd.DataFrame,
    *,
    feature_names: list[str] | None = None,
) -> pd.DataFrame:
    """
    Coerce the runtime decision frame into the exact schema CatBoost expects.
    将运行时决策特征表强制规整为 CatBoost 期望的精确 schema。
    """
    ordered_feature_names = list(feature_names or [*list(DECISION_NUMERIC_FEATURES), *list(DECISION_CATEGORICAL_FEATURES)])
    normalized = frame.copy()
    for feature_name in ordered_feature_names:
        if feature_name not in normalized.columns:
            normalized[feature_name] = 0.0 if feature_name in DECISION_NUMERIC_FEATURES else ""
    for feature_name in DECISION_NUMERIC_FEATURES:
        if feature_name in normalized.columns:
            normalized[feature_name] = pd.to_numeric(normalized[feature_name], errors="coerce").fillna(0.0).astype(float)
    for feature_name in DECISION_CATEGORICAL_FEATURES:
        if feature_name in normalized.columns:
            normalized[feature_name] = normalized[feature_name].fillna("").map(lambda value: str(value))
    return normalized[ordered_feature_names]


def build_decision_inference_frame(
    feature_row: dict[str, Any],
    *,
    feature_names: list[str] | None = None,
) -> pd.DataFrame:
    frame = rows_to_feature_frame([feature_row])
    return normalize_decision_feature_frame(frame, feature_names=feature_names)
