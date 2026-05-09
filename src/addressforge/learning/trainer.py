from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from addressforge.core.common import (
    canonicalize_unit_number,
    create_run,
    dumps_payload,
    fetch_all,
    finish_run,
    normalize_street_name,
)
from addressforge.core.config import (
    ADDRESSFORGE_MODEL_ARTIFACT_DIR,
    ADDRESSFORGE_MODEL_FAMILY,
    ADDRESSFORGE_WORKSPACE_NAME,
)
from addressforge.core.utils import logger
from addressforge.learning.canada_benchmark import run_canada_address_benchmark
from addressforge.models import get_model, get_workspace, register_model_version

_APARTMENT_UNIT_HINT_RE = re.compile(
    r"(?:\b(?:APT|APART|SUITE|STE|UNIT|ROOM|RM|FLOOR|FL|BASEMENT|BSMT|LOWER|UPPER|PENTHOUSE|PH|GF|GROUND FLOOR|MAIN FLOOR|MAIN FLR|REAR|FRONT|SIDE)\b|#\s*[A-Z0-9]+)",
    re.IGNORECASE,
)

_STRONG_RESIDENTIAL_UNIT_HINT_RE = re.compile(
    r"(?:\b(?:APT|APARTMENT|UNIT|SUITE|STE|ROOM|RM|FLOOR|FL|BASEMENT|BSMT|PENTHOUSE|PH|REAR|FRONT)\b|#\s*[A-Z0-9]+)",
    re.IGNORECASE,
)

_GEOGRAPHIC_MODIFIER_PLACE_RE = re.compile(
    r"\b(?:UPPER|LOWER)\s+[A-Z][A-Z' -]{2,}\b",
    re.IGNORECASE,
)

_RESIDENTIAL_LIKE_HINT_RE = re.compile(
    r"\b(?:APT|APARTMENT|UNIT|BASEMENT|BSMT|UPPER|LOWER|REAR|FRONT|PENTHOUSE|PH)\b",
    re.IGNORECASE,
)

_EXPLICIT_UNIT_KEYWORD_RE = re.compile(
    r"(?:\b(?:APT|APARTMENT|UNIT|SUITE|STE|ROOM|RM|FLOOR|FL|BASEMENT|BSMT|PENTHOUSE|PH|REAR|FRONT)\b|#\s*[A-Z0-9]+)",
    re.IGNORECASE,
)

_POSTAL_CODE_RE = re.compile(r"\b[A-Z]\d[A-Z]\s*\d[A-Z]\d\b", re.IGNORECASE)

_DOUBLE_NUMBER_RE = re.compile(r"\b\d+[A-Z]?\b")

_NUMBERED_ROAD_RE = re.compile(r"\b(?:HWY|HIGHWAY|ROUTE|RTE|TRUNK)\s+\d+[A-Z]?\b|\b(?:NS|NB|PE|NL|QC|ON|MB|SK|AB|BC|YT|NT|NU)-\d+[A-Z]?\b|\bCANADA\s+\d+[A-Z]?\b", re.IGNORECASE)


def _artifact_dir() -> Path:
    return Path(os.getenv("ADDRESSFORGE_MODEL_ARTIFACT_DIR", ADDRESSFORGE_MODEL_ARTIFACT_DIR)).expanduser()


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_sample_pool_name(notes: str) -> str:
    notes_text = str(notes or "")
    match = re.search(r"\[sample_pool=([a-z_]+)\]", notes_text, re.IGNORECASE)
    if not match:
        return ""
    return str(match.group(1) or "").strip().lower()


_SEMANTIC_TASK_TYPES = {
    "review",
    "building_type",
    "unit_number",
    "commercial",
    "single_unit",
    "decision",
    "validation",
}


def _normalize_training_task_type(task_type: str, notes: str = "") -> str:
    normalized = str(task_type or "").strip().lower()
    if normalized in _SEMANTIC_TASK_TYPES:
        return normalized
    pool = _extract_sample_pool_name(notes)
    if pool:
        return "review"
    if normalized.startswith(("calibration_", "unit_boost_", "hard_correction_")):
        return "review"
    return normalized or "unknown"


def _has_double_number_without_explicit_unit(raw_text: str) -> bool:
    text = str(raw_text or "").upper()
    if not text:
        return False
    text = _POSTAL_CODE_RE.sub(" ", text)
    if _EXPLICIT_UNIT_KEYWORD_RE.search(text):
        return False
    return len(_DOUBLE_NUMBER_RE.findall(text)) >= 2


def _derive_row_learning_weight(row: dict[str, Any], label: dict[str, Any] | None = None) -> float:
    label = label if isinstance(label, dict) else {}
    notes = str(row.get("notes") or "")
    raw_text = str(row.get("raw_address_text") or "")
    task_type = _normalize_training_task_type(row.get("task_type") or "", notes)
    source_name = str(row.get("source_name") or "").strip().lower()
    building_type = str(label.get("building_type") or label.get("structure_type") or "").strip().lower()
    sample_pool = _extract_sample_pool_name(notes)
    has_explicit_unit_hint = bool(_EXPLICIT_UNIT_KEYWORD_RE.search(raw_text))
    has_double_number_without_unit = _has_double_number_without_explicit_unit(raw_text)
    is_numbered_road = bool(_NUMBERED_ROAD_RE.search(str(raw_text or "").upper()))

    pool_weights = {
        "calibration_single_unit": 1.0,
        "calibration_multi_unit": 1.0,
        "unit_boost": 0.9,
        "hard_correction": 0.7,
    }
    if sample_pool:
        weight = pool_weights.get(sample_pool, 0.85)
    else:
        if task_type == "review":
            weight = 0.5
        elif task_type in {"building_type", "unit_number", "commercial", "single_unit"}:
            weight = 0.85
        else:
            weight = 1.0

    if source_name == "gold_relabel":
        weight = max(weight, 0.9)

    if task_type == "review" and has_double_number_without_unit:
        weight = min(weight, 0.5)
    if task_type == "review" and is_numbered_road and building_type == "single_unit":
        weight = min(weight, 0.5)
    if building_type == "multi_unit" and has_explicit_unit_hint:
        weight = max(weight, 0.95)
    if building_type == "commercial" and has_explicit_unit_hint:
        weight = max(weight, 0.9)

    return round(max(0.35, min(weight, 1.1)), 4)

def _derive_decision_policy(workspace_name: str) -> dict[str, float]:
    # (Existing logic to collect scores...)
    # (现有收集分数的逻辑...)
    # ...
    # Adaptive Threshold Adjustment (Regression Mitigation)
    # 自适应阈值调整 (回归缓解)
    # If the system detects weak signals for apartments, lower the acceptance barrier
    # 如果系统检测到公寓信号微弱，降低接受门槛
    if len(multi_unit_accept_scores) > 0:
        mu_median = sorted(multi_unit_accept_scores)[len(multi_unit_accept_scores) // 2]
        defaults["multi_unit_accept_threshold"] = min(defaults["multi_unit_accept_threshold"], round(mu_median - 0.05, 3))
    
    if len(commercial_accept_scores) > 0:
        comm_median = sorted(commercial_accept_scores)[len(commercial_accept_scores) // 2]
        defaults["commercial_accept_threshold"] = min(defaults["commercial_accept_threshold"], round(comm_median - 0.05, 3))

    return defaults



def _load_candidate_list_from_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw_address_text = str(row.get("raw_address_text") or "").strip()
    if raw_address_text:
        try:
            from addressforge.api.server import AddressPlatformService, AddressRequest, RerankerArtifactLoader

            service = AddressPlatformService()
            original_loader = RerankerArtifactLoader.load_decision_policy
            RerankerArtifactLoader.load_decision_policy = staticmethod(lambda *args, **kwargs: {})
            try:
                parsed = service.parse(
                    AddressRequest(
                        raw_address_text=raw_address_text,
                        city=row.get("city"),
                        province=row.get("province"),
                        postal_code=row.get("postal_code"),
                        country_code=row.get("country_code") or "CA",
                    )
                )
            finally:
                RerankerArtifactLoader.load_decision_policy = original_loader
            candidates = parsed.get("candidates") or []
            if isinstance(candidates, list) and candidates:
                return [item for item in candidates if isinstance(item, dict)]
        except Exception:
            pass
    try:
        parser_json = json.loads(row.get("parser_json") or "{}")
    except Exception:
        parser_json = {}
    if isinstance(parser_json, dict):
        candidates = parser_json.get("candidates") or []
        best_candidate = parser_json.get("best_candidate") or {}
        if isinstance(candidates, list) and candidates:
            return [item for item in candidates if isinstance(item, dict)]
        if isinstance(best_candidate, dict) and best_candidate:
            return [best_candidate]
    return []


def _derive_decision_policy(workspace_name: str) -> dict[str, float]:
    defaults = {
        "close_candidate_delta": 0.08,
        "commercial_accept_threshold": 0.88,
        "multi_unit_accept_threshold": 0.72,
        "parser_disagreement_review_threshold": 0.72,
        "commercial_review_threshold": 0.72,
        "high_confidence_accept_threshold": 0.82,
        "moderate_confidence_review_threshold": 0.62,
        "gps_weak_match_threshold": 0.62,
        "gps_conflict_threshold": 0.5,
    }
    rows = fetch_all(
        """
        SELECT
            g.label_json,
            g.task_type,
            g.notes,
            g.source_name,
            acr.validation_json,
            acr.raw_address_text,
            acr.building_type
        FROM gold_label g
        JOIN (
            SELECT source_id, MAX(gold_label_id) AS latest_gold_label_id
            FROM gold_label
            WHERE workspace_name = %s
              AND review_status = 'accepted'
              AND label_source = 'human'
            GROUP BY source_id
        ) latest
          ON latest.latest_gold_label_id = g.gold_label_id
        JOIN address_cleaning_result acr
          ON acr.workspace_name = g.workspace_name
         AND CAST(acr.raw_id AS CHAR) = g.source_id
        WHERE g.workspace_name = %s
          AND g.review_status = 'accepted'
          AND g.label_source = 'human'
        ORDER BY g.gold_label_id ASC
        """,
        (workspace_name, workspace_name),
    )
    commercial_accept_scores: list[tuple[float, float]] = []
    multi_unit_accept_scores: list[tuple[float, float]] = []
    accept_scores: list[tuple[float, float]] = []
    review_scores: list[tuple[float, float]] = []
    reject_scores: list[tuple[float, float]] = []
    gps_reference_scores: list[tuple[float, float]] = []

    for row in rows:
        try:
            label = json.loads(row.get("label_json") or "{}")
            validation = json.loads(row.get("validation_json") or "{}")
        except Exception:
            continue
        if not isinstance(label, dict) or not isinstance(validation, dict):
            continue
        row_weight = _derive_row_learning_weight(row, label)
        gold_decision = str(label.get("decision") or "").strip().lower()
        gold_building = str(label.get("building_type") or "").strip().lower()
        score = _safe_float(validation.get("confidence"), 0.0)
        ref_score = _safe_float((validation.get("hints") or {}).get("reference_score"), 0.0)
        if gold_decision == "accept":
            accept_scores.append((score, row_weight))
            if gold_building == "commercial":
                commercial_accept_scores.append((score, row_weight))
            if gold_building == "multi_unit":
                multi_unit_accept_scores.append((score, row_weight))
        elif gold_decision == "review":
            review_scores.append((score, row_weight))
        elif gold_decision == "reject":
            reject_scores.append((score, row_weight))
        if ref_score > 0:
            gps_reference_scores.append((ref_score, row_weight))

    policy = dict(defaults)
    
    def _weighted_percentile_low(scores: list[tuple[float, float]], p: float = 0.1) -> float | None:
        if not scores:
            return None
        sorted_scores = sorted(scores, key=lambda item: item[0])
        total_weight = sum(max(weight, 0.0) for _, weight in sorted_scores)
        if total_weight <= 0:
            return sorted_scores[0][0]
        target = total_weight * p
        running = 0.0
        for value, weight in sorted_scores:
            running += max(weight, 0.0)
            if running >= target:
                return value
        return sorted_scores[-1][0]

    # Use robust P10 (10th percentile) to avoid outliers dragging thresholds too low/high
    # 使用稳健的 P10 (第 10 百分位数) 避免离群值将阈值拉得太低/太高
    if commercial_accept_scores:
        p10 = _weighted_percentile_low(commercial_accept_scores, 0.1)
        policy["commercial_accept_threshold"] = round(max(0.65, p10 - 0.01), 4)
    if multi_unit_accept_scores:
        p10 = _weighted_percentile_low(multi_unit_accept_scores, 0.1)
        # SENSITIVITY BOOST: If few samples exist, lower the bar further to improve recall
        # 灵敏度增强：如果样本较少，进一步降低门槛以提高召回率
        effective_multi_unit_weight = sum(weight for _, weight in multi_unit_accept_scores)
        boost = 0.05 if effective_multi_unit_weight < 50 else 0.0
        policy["multi_unit_accept_threshold"] = round(max(0.50, p10 - 0.01 - boost), 4)
    
    if accept_scores:
        p10 = _weighted_percentile_low(accept_scores, 0.1)
        policy["high_confidence_accept_threshold"] = round(max(0.60, p10 - 0.01), 4)

    if review_scores:
        lowest_review = _weighted_percentile_low(review_scores, 0.1)
        policy["moderate_confidence_review_threshold"] = round(max(0.35, lowest_review - 0.01), 4)
        policy["parser_disagreement_review_threshold"] = policy["moderate_confidence_review_threshold"]
        policy["commercial_review_threshold"] = policy["moderate_confidence_review_threshold"]

    if reject_scores:
        candidate = round(max(value for value, _ in reject_scores) + 0.01, 4)
        policy["moderate_confidence_review_threshold"] = max(policy["moderate_confidence_review_threshold"], candidate)

    if gps_reference_scores:
        weakest_reference = _weighted_percentile_low(gps_reference_scores, 0.1)
        policy["gps_weak_match_threshold"] = round(max(0.5, weakest_reference), 4)
        policy["gps_conflict_threshold"] = round(max(0.4, weakest_reference - 0.05), 4)
    
    logger.info("Derived Decision Policy (Adaptive): %s", policy)
    return policy


def _derive_parser_weights(
    workspace_name: str,
    *,
    model_name: str,
    model_version: str,
    profile: str,
    decision_policy: dict[str, float],
) -> dict[str, float]:
    benchmark_path = Path(__file__).resolve().parents[3] / "examples" / "canada_address_benchmark.jsonl"
    parsers = ("simple_rule", "hybrid_canada", "libpostal")
    if not benchmark_path.exists():
        return {parser_name: round(1.0 / len(parsers), 4) for parser_name in parsers}
    scores: dict[str, float] = {}
    for parser_name in parsers:
        benchmark = run_canada_address_benchmark(
            benchmark_path,
            workspace_name=workspace_name,
            model_name=model_name,
            model_version=model_version,
            profile=profile,
            parsers=(parser_name,),
            decision_policy=decision_policy,
        )
        metrics = benchmark.get("metrics") or {}
        fields = ("street_number", "street_name", "unit_number", "building_type", "decision")
        values = [float((metrics.get(field) or {}).get("accuracy") or 0.0) for field in fields]
        score = sum(values) / len(values) if values else 0.0
        scores[parser_name] = round(score, 4)
    total = sum(scores.values())
    if total <= 0:
        return {parser_name: round(1.0 / len(parsers), 4) for parser_name in parsers}
    return {parser_name: round(value / total, 4) for parser_name, value in scores.items()}


def _derive_match_rule_weights(workspace_name: str) -> dict[str, float]:
    rows = fetch_all(
        """
        SELECT
            g.label_json,
            acr.parser_json,
            acr.validation_json,
            acr.building_type,
            acr.suggested_unit_number,
            acr.decision,
            r.raw_address_text,
            r.city,
            r.province,
            r.postal_code,
            r.country_code
        FROM gold_label g
        JOIN (
            SELECT source_id, MAX(gold_label_id) AS latest_gold_label_id
            FROM gold_label
            WHERE workspace_name = %s
              AND review_status = 'accepted'
              AND label_source = 'human'
            GROUP BY source_id
        ) latest
          ON latest.latest_gold_label_id = g.gold_label_id
        JOIN address_cleaning_result acr
          ON acr.workspace_name = g.workspace_name
         AND CAST(acr.raw_id AS CHAR) = g.source_id
        LEFT JOIN raw_address_record r
          ON r.workspace_name = g.workspace_name
         AND (CAST(r.raw_id AS CHAR) = g.source_id OR r.external_id = g.source_id)
        WHERE g.workspace_name = %s
        ORDER BY g.gold_label_id ASC
        """,
        (workspace_name, workspace_name),
    )
    stats: dict[str, dict[str, float]] = {}
    unit_present_total = 0.0
    unit_present_correct = 0.0
    unit_keyword_total = 0.0
    unit_keyword_positive = 0.0
    residential_hint_total = 0.0
    residential_hint_positive = 0.0
    commercial_hint_total = 0.0
    commercial_hint_positive = 0.0
    for row in rows:
        try:
            label = json.loads(row.get("label_json") or "{}")
        except Exception:
            continue
        if not isinstance(label, dict):
            continue
        row_weight = _derive_row_learning_weight(row, label)
        candidates = _load_candidate_list_from_row(row)
        if not candidates:
            continue
        best_candidate = candidates[0]
        best_parsed = best_candidate.get("parsed") or {}
        feature_vector = best_parsed.get("feature_vector") or {}
        raw_text = str(row.get("raw_address_text") or "")
        gold_decision = str(label.get("decision") or "").strip().lower()
        if gold_decision == "correct":
            gold_decision = "accept"
        predicted_decision = str(row.get("decision") or "").strip().lower()
        gold_building = str(label.get("building_type") or label.get("structure_type") or "").strip().lower()
        predicted_building = str(row.get("building_type") or "").strip().lower()
        gold_unit = str(label.get("unit_number") or label.get("suggested_unit_number") or "").strip().upper()
        predicted_unit = str(row.get("suggested_unit_number") or "").strip().upper()
        components: list[float] = [
            1.0 if predicted_decision == gold_decision else 0.0,
            1.0 if predicted_building == gold_building else 0.0,
        ]
        if gold_unit or predicted_unit:
            unit_correct = 1.0 if predicted_unit == gold_unit else 0.0
            components.append(unit_correct)
            unit_present_total += row_weight
            unit_present_correct += unit_correct * row_weight
        score = sum(components) / len(components)
        rule_keys = []
        pattern = feature_vector.get("pattern")
        if pattern:
            rule_keys.append(str(pattern))
        unit_source = best_parsed.get("unit_source")
        if unit_source:
            rule_keys.append(str(unit_source))
        seen: set[str] = set()
        for rule_key in rule_keys:
            if rule_key in seen:
                continue
            seen.add(rule_key)
            bucket = stats.setdefault(rule_key, {"total": 0.0, "score": 0.0})
            bucket["total"] += row_weight
            bucket["score"] += score * row_weight
        has_explicit_unit_hint = bool(feature_vector.get("has_explicit_unit_hint")) or bool(
            re.search(r"\b(?:SUITE|STE|UNIT|APT|APARTMENT|ROOM|RM|FLOOR|FL|#)\b", raw_text.upper())
        )
        has_residential_unit_hint = bool(feature_vector.get("has_residential_unit_hint"))
        has_commercial_hint = bool(feature_vector.get("has_commercial_unit_hint")) or bool(feature_vector.get("is_commercial"))
        if has_explicit_unit_hint:
            unit_keyword_total += row_weight
            if gold_unit:
                unit_keyword_positive += row_weight
        if has_residential_unit_hint:
            residential_hint_total += row_weight
            if gold_unit or gold_building == "multi_unit":
                residential_hint_positive += row_weight
        if has_commercial_hint:
            commercial_hint_total += row_weight
            if gold_building == "commercial":
                commercial_hint_positive += row_weight
    weights: dict[str, float] = {}
    for rule_key, bucket in stats.items():
        total = bucket["total"]
        if total < 2:
            continue
        weights[rule_key] = round(bucket["score"] / total, 4)
    if unit_present_total > 0:
        weights["__unit_present__"] = round(unit_present_correct / unit_present_total, 4)
    if unit_keyword_total > 0:
        weights["__unit_keyword_present__"] = round(unit_keyword_positive / unit_keyword_total, 4)
    if residential_hint_total > 0:
        weights["__residential_unit_hint__"] = round(residential_hint_positive / residential_hint_total, 4)
    if commercial_hint_total > 0:
        weights["__commercial_hint__"] = round(commercial_hint_positive / commercial_hint_total, 4)
    return weights


def _derive_candidate_feature_weights(workspace_name: str) -> dict[str, float]:
    rows = fetch_all(
        """
        SELECT
            g.label_json,
            acr.parser_json,
            r.raw_address_text,
            r.city,
            r.province,
            r.postal_code,
            r.country_code
        FROM gold_label g
        JOIN (
            SELECT source_id, MAX(gold_label_id) AS latest_gold_label_id
            FROM gold_label
            WHERE workspace_name = %s
              AND review_status = 'accepted'
              AND label_source = 'human'
            GROUP BY source_id
        ) latest
          ON latest.latest_gold_label_id = g.gold_label_id
        JOIN address_cleaning_result acr
          ON acr.workspace_name = g.workspace_name
         AND CAST(acr.raw_id AS CHAR) = g.source_id
        LEFT JOIN raw_address_record r
          ON r.workspace_name = g.workspace_name
         AND (CAST(r.raw_id AS CHAR) = g.source_id OR r.external_id = g.source_id)
        WHERE g.workspace_name = %s
        ORDER BY g.gold_label_id ASC
        """,
        (workspace_name, workspace_name),
    )
    feature_stats: dict[str, dict[str, float]] = {}
    for row in rows:
        try:
            label = json.loads(row.get("label_json") or "{}")
        except Exception:
            continue
        if not isinstance(label, dict):
            continue
        row_weight = _derive_row_learning_weight(row, label)
        candidates = _load_candidate_list_from_row(row)
        if not isinstance(candidates, list) or not candidates:
            continue

        gold_street_number = str(label.get("street_number") or (label.get("canonical") or {}).get("street_number") or "").strip()
        gold_street_name = normalize_street_name(
            label.get("street_name") or (label.get("canonical") or {}).get("street_name")
        )
        gold_unit = canonicalize_unit_number(
            label.get("unit_number")
            or label.get("suggested_unit_number")
            or (label.get("canonical") or {}).get("unit_number")
        )
        gold_building = str(label.get("building_type") or label.get("structure_type") or "").strip().lower()
        raw_text = str(row.get("raw_address_text") or "").upper()
        normalized_raw_text = re.sub(r"\s+", " ", raw_text)

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            parsed = candidate.get("parsed") if isinstance(candidate.get("parsed"), dict) else candidate
            if not isinstance(parsed, dict):
                continue
            feature_vector = parsed.get("feature_vector") or {}
            candidate_street_number = str(parsed.get("street_number") or "").strip()
            candidate_street_name = normalize_street_name(parsed.get("street_name"))
            candidate_unit = canonicalize_unit_number(parsed.get("unit_number"))

            components: list[float] = []
            if gold_street_number:
                components.append(1.0 if candidate_street_number == gold_street_number else 0.0)
            if gold_street_name:
                components.append(1.0 if candidate_street_name == gold_street_name else 0.0)
            if gold_unit or candidate_unit:
                components.append(1.0 if candidate_unit == gold_unit else 0.0)
            if gold_building == "multi_unit":
                components.append(1.0 if candidate_unit else 0.0)
            elif gold_building == "single_unit":
                components.append(1.0 if not candidate_unit and not feature_vector.get("is_commercial") else 0.0)
            elif gold_building == "commercial":
                components.append(1.0 if feature_vector.get("is_commercial") else 0.0)
            if not components:
                continue
            candidate_score = sum(components) / len(components)

            feature_keys: list[str] = []
            if candidate_street_number and candidate_street_name:
                feature_keys.append("__candidate_complete_street__")
            if candidate_unit:
                feature_keys.append("__candidate_has_unit__")
            if candidate_street_name and candidate_street_name.upper() in normalized_raw_text:
                feature_keys.append("__candidate_street_text_alignment__")
            has_explicit_unit_hint = bool(feature_vector.get("has_explicit_unit_hint")) or bool(
                re.search(r"\b(?:SUITE|STE|UNIT|APT|APARTMENT|ROOM|RM|FLOOR|FL|#)\b", raw_text)
            )
            has_residential_unit_hint = bool(feature_vector.get("has_residential_unit_hint"))
            has_geographic_modifier_only = bool(feature_vector.get("has_geographic_modifier_only"))
            has_double_number_pattern = bool(feature_vector.get("has_double_number_pattern"))
            is_numbered_road_name = bool(feature_vector.get("is_numbered_road_name"))
            has_commercial_hint = bool(feature_vector.get("has_commercial_unit_hint")) or bool(feature_vector.get("is_commercial"))
            unit_text_aligned = bool(
                candidate_unit
                and (
                    re.search(
                        rf"\b(?:SUITE|STE|UNIT|APT|APARTMENT|ROOM|RM|FLOOR|FL|#)\s*{re.escape(candidate_unit)}\b",
                        normalized_raw_text,
                    )
                    or re.search(rf"\b{re.escape(candidate_unit)}\b", normalized_raw_text)
                )
            )
            if has_explicit_unit_hint and candidate_unit:
                feature_keys.append("__candidate_unit_with_hint__")
            if (has_explicit_unit_hint or has_residential_unit_hint) and not candidate_unit:
                feature_keys.append("__candidate_missing_unit_with_hint__")
            if has_residential_unit_hint and not has_geographic_modifier_only:
                feature_keys.append("__candidate_residential_alignment__")
            if has_geographic_modifier_only:
                feature_keys.append("__candidate_geographic_modifier_only__")
            if candidate_unit and has_double_number_pattern and not has_explicit_unit_hint:
                if not feature_vector.get("has_bare_trailing_unit_city_pattern"):
                    feature_keys.append("__candidate_bare_number_without_unit_hint__")
            if candidate_unit and feature_vector.get("has_bare_trailing_unit_city_pattern"):
                feature_keys.append("__candidate_bare_trailing_unit_city__")
            if is_numbered_road_name:
                feature_keys.append("__candidate_numbered_road_name__")
            if has_commercial_hint:
                feature_keys.append("__candidate_commercial_alignment__")
            if unit_text_aligned:
                feature_keys.append("__candidate_unit_text_alignment__")

            for feature_key in feature_keys:
                bucket = feature_stats.setdefault(feature_key, {"total": 0.0, "score": 0.0})
                bucket["total"] += row_weight
                bucket["score"] += candidate_score * row_weight

    weights: dict[str, float] = {}
    for feature_key, bucket in feature_stats.items():
        if bucket["total"] < 2:
            continue
        weights[feature_key] = round(bucket["score"] / bucket["total"], 4)
    return weights


def _derive_candidate_pair_weights(workspace_name: str) -> dict[str, float]:
    rows = fetch_all(
        """
        SELECT
            g.label_json,
            acr.parser_json,
            r.raw_address_text,
            r.city,
            r.province,
            r.postal_code,
            r.country_code
        FROM gold_label g
        JOIN (
            SELECT source_id, MAX(gold_label_id) AS latest_gold_label_id
            FROM gold_label
            WHERE workspace_name = %s
              AND review_status = 'accepted'
              AND label_source = 'human'
            GROUP BY source_id
        ) latest
          ON latest.latest_gold_label_id = g.gold_label_id
        JOIN address_cleaning_result acr
          ON acr.workspace_name = g.workspace_name
         AND CAST(acr.raw_id AS CHAR) = g.source_id
        LEFT JOIN raw_address_record r
          ON r.workspace_name = g.workspace_name
         AND (CAST(r.raw_id AS CHAR) = g.source_id OR r.external_id = g.source_id)
        WHERE g.workspace_name = %s
        ORDER BY g.gold_label_id ASC
        """,
        (workspace_name, workspace_name),
    )
    pair_stats: dict[str, dict[str, float]] = {}
    for row in rows:
        try:
            label = json.loads(row.get("label_json") or "{}")
        except Exception:
            continue
        if not isinstance(label, dict):
            continue
        row_weight = _derive_row_learning_weight(row, label)
        candidates = _load_candidate_list_from_row(row)
        if not isinstance(candidates, list) or len(candidates) < 2:
            continue

        gold_street_number = str(label.get("street_number") or (label.get("canonical") or {}).get("street_number") or "").strip()
        gold_street_name = normalize_street_name(
            label.get("street_name") or (label.get("canonical") or {}).get("street_name")
        )
        gold_unit = canonicalize_unit_number(
            label.get("unit_number")
            or label.get("suggested_unit_number")
            or (label.get("canonical") or {}).get("unit_number")
        )
        gold_building = str(label.get("building_type") or label.get("structure_type") or "").strip().lower()
        raw_text = str(row.get("raw_address_text") or "").upper()

        scored_candidates: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            parsed = candidate.get("parsed") if isinstance(candidate.get("parsed"), dict) else candidate
            if not isinstance(parsed, dict):
                continue
            feature_vector = parsed.get("feature_vector") or {}
            candidate_street_number = str(parsed.get("street_number") or "").strip()
            candidate_street_name = normalize_street_name(parsed.get("street_name"))
            candidate_unit = canonicalize_unit_number(parsed.get("unit_number"))
            components: list[float] = []
            if gold_street_number:
                components.append(1.0 if candidate_street_number == gold_street_number else 0.0)
            if gold_street_name:
                components.append(1.0 if candidate_street_name == gold_street_name else 0.0)
            if gold_unit or candidate_unit:
                components.append(1.0 if candidate_unit == gold_unit else 0.0)
            if gold_building == "multi_unit":
                components.append(1.0 if candidate_unit else 0.0)
            elif gold_building == "single_unit":
                components.append(1.0 if not candidate_unit and not feature_vector.get("is_commercial") else 0.0)
            elif gold_building == "commercial":
                components.append(1.0 if feature_vector.get("is_commercial") else 0.0)
            if not components:
                continue
            candidate_score = sum(components) / len(components)
            scored_candidates.append((candidate_score, parsed, feature_vector))
        if len(scored_candidates) < 2:
            continue
        scored_candidates.sort(key=lambda item: item[0], reverse=True)
        winner_score, winner_parsed, winner_features = scored_candidates[0]
        loser_score, loser_parsed, loser_features = scored_candidates[-1]
        if winner_score <= loser_score:
            continue
        winner_unit = canonicalize_unit_number(winner_parsed.get("unit_number"))
        loser_unit = canonicalize_unit_number(loser_parsed.get("unit_number"))

        comparisons = {
            "__prefer_unit_candidate__": bool(winner_unit and not loser_unit),
            "__penalize_missing_unit_candidate__": bool(not winner_unit and loser_unit),
            "__prefer_text_aligned_unit__": bool(
                winner_unit
                and re.search(rf"\b{re.escape(winner_unit)}\b", raw_text)
                and (not loser_unit or not re.search(rf"\b{re.escape(loser_unit)}\b", raw_text))
            ),
            "__prefer_complete_street_candidate__": bool(
                winner_parsed.get("street_number")
                and winner_parsed.get("street_name")
                and not (loser_parsed.get("street_number") and loser_parsed.get("street_name"))
            ),
            "__prefer_residential_unit_candidate__": bool(
                winner_features.get("has_residential_unit_hint")
                and not winner_features.get("has_geographic_modifier_only")
                and winner_unit
                and not loser_unit
            ),
            "__penalize_geographic_modifier_candidate__": bool(
                winner_features.get("has_geographic_modifier_only") and not winner_unit and loser_unit
            ),
            "__penalize_bare_number_unit_candidate__": bool(
                winner_unit
                and winner_features.get("has_double_number_pattern")
                and not winner_features.get("has_explicit_unit_hint")
                and not winner_features.get("has_bare_trailing_unit_city_pattern")
                and not loser_unit
            ),
            "__prefer_bare_trailing_unit_city_candidate__": bool(
                winner_unit
                and winner_features.get("has_bare_trailing_unit_city_pattern")
                and not loser_unit
            ),
            "__penalize_numbered_road_unit_candidate__": bool(
                winner_unit
                and winner_features.get("is_numbered_road_name")
                and not loser_unit
            ),
        }
        margin = winner_score - loser_score
        for feature_key, enabled in comparisons.items():
            if not enabled:
                continue
            bucket = pair_stats.setdefault(feature_key, {"total": 0.0, "score": 0.0})
            bucket["total"] += row_weight
            bucket["score"] += margin * row_weight

    weights: dict[str, float] = {}
    for feature_key, bucket in pair_stats.items():
        if bucket["total"] < 1:
            continue
        avg_margin = bucket["score"] / bucket["total"]
        support = bucket["total"] / (bucket["total"] + 2.0)
        weights[feature_key] = round(min(max(0.5 + avg_margin * support * 0.5, 0.0), 1.0), 4)
    return weights


def _derive_hard_sample_profile(workspace_name: str) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT
            g.source_id,
            g.task_type,
            g.source_name,
            g.notes,
            g.label_json,
            r.raw_address_text
        FROM gold_label g
        JOIN (
            SELECT source_id, MAX(gold_label_id) AS latest_gold_label_id
            FROM gold_label
            WHERE workspace_name = %s
              AND review_status = 'accepted'
              AND label_source = 'human'
            GROUP BY source_id
        ) latest
          ON latest.latest_gold_label_id = g.gold_label_id
        LEFT JOIN raw_address_record r
          ON r.workspace_name = g.workspace_name
         AND (CAST(r.raw_id AS CHAR) = g.source_id OR r.external_id = g.source_id)
        WHERE g.workspace_name = %s
          AND g.review_status = 'accepted'
          AND g.label_source = 'human'
        ORDER BY g.gold_label_id ASC
        """,
        (workspace_name, workspace_name),
    )
    total = len(rows)
    hard_sample_count = 0
    unit_hint_count = 0
    multi_unit_count = 0
    hard_task_type_count = 0
    sample_pool_counts: dict[str, int] = {}
    sample_pool_weight_totals: dict[str, float] = {}
    source_name_counts: dict[str, int] = {}
    task_type_counts: dict[str, int] = {}
    effective_training_weight_total = 0.0
    for row in rows:
        try:
            label = json.loads(row.get("label_json") or "{}")
        except Exception:
            label = {}
        row_weight = _derive_row_learning_weight(row, label)
        effective_training_weight_total += row_weight
        source_name = str(row.get("source_name") or "unknown")
        notes = str(row.get("notes") or "")
        task_type = _normalize_training_task_type(row.get("task_type") or "unknown", notes)
        raw_text = str(row.get("raw_address_text") or "").upper()
        building_type = str(label.get("building_type") or label.get("structure_type") or "").strip().lower()
        source_name_counts[source_name] = source_name_counts.get(source_name, 0) + 1
        task_type_counts[task_type] = task_type_counts.get(task_type, 0) + 1
        pool_match = re.search(r"\[sample_pool=([a-z_]+)\]", notes, re.IGNORECASE)
        if pool_match:
            pool_name = str(pool_match.group(1) or "").strip().lower()
            if pool_name:
                sample_pool_counts[pool_name] = sample_pool_counts.get(pool_name, 0) + 1
                sample_pool_weight_totals[pool_name] = round(
                    sample_pool_weight_totals.get(pool_name, 0.0) + row_weight,
                    4,
                )
        has_unit_hint = bool(_APARTMENT_UNIT_HINT_RE.search(raw_text))
        if has_unit_hint:
            unit_hint_count += 1
        if building_type == "multi_unit":
            multi_unit_count += 1
        is_hard_task_type = task_type in {"unit_number", "building_type"}
        if is_hard_task_type:
            hard_task_type_count += 1
        if has_unit_hint or building_type == "multi_unit" or is_hard_task_type:
            hard_sample_count += 1
    return {
        "total_gold": total,
        "hard_sample_gold": hard_sample_count,
        "hard_sample_ratio": round(hard_sample_count / total, 4) if total else 0.0,
        "unit_hint_gold": unit_hint_count,
        "multi_unit_gold": multi_unit_count,
        "hard_task_type_gold": hard_task_type_count,
        "sample_pool_counts": sample_pool_counts,
        "sample_pool_weight_totals": sample_pool_weight_totals,
        "calibration_pool_gold": sum(count for pool, count in sample_pool_counts.items() if pool.startswith("calibration_")),
        "correction_pool_gold": sum(
            count for pool, count in sample_pool_counts.items() if pool in {"unit_boost", "hard_correction"}
        ),
        "effective_training_weight_total": round(effective_training_weight_total, 4),
        "source_name_counts": source_name_counts,
        "task_type_counts": task_type_counts,
    }


def _looks_like_geographic_upper_lower_only(raw_text: str) -> bool:
    text = str(raw_text or "").strip()
    if not text:
        return False
    if not _GEOGRAPHIC_MODIFIER_PLACE_RE.search(text):
        return False
    return not bool(re.search(r"\b(?:APT|UNIT|SUITE|STE|ROOM|RM|#)\b", text, re.IGNORECASE))


def _derive_label_consistency_diagnostics(workspace_name: str, example_limit: int = 20) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT
            g.source_id,
            g.task_type,
            g.source_name,
            g.label_json,
            r.raw_address_text
        FROM gold_label g
        JOIN (
            SELECT source_id, MAX(gold_label_id) AS latest_gold_label_id
            FROM gold_label
            WHERE workspace_name = %s
              AND review_status = 'accepted'
              AND label_source = 'human'
            GROUP BY source_id
        ) latest
          ON latest.latest_gold_label_id = g.gold_label_id
        LEFT JOIN raw_address_record r
          ON r.workspace_name = g.workspace_name
         AND (CAST(r.raw_id AS CHAR) = g.source_id OR r.external_id = g.source_id)
        WHERE g.workspace_name = %s
          AND g.review_status = 'accepted'
          AND g.label_source = 'human'
        ORDER BY g.gold_label_id ASC
        """,
        (workspace_name, workspace_name),
    )

    single_unit_with_strong_unit_hint: list[dict[str, Any]] = []
    multi_unit_without_unit_evidence: list[dict[str, Any]] = []
    commercial_with_residential_pattern: list[dict[str, Any]] = []

    for row in rows:
        try:
            label = json.loads(row.get("label_json") or "{}")
        except Exception:
            label = {}
        raw_text = str(row.get("raw_address_text") or "")
        building_type = str(label.get("building_type") or label.get("structure_type") or "").strip().lower()
        unit_number = str(
            label.get("unit_number")
            or label.get("suggested_unit_number")
            or ((label.get("canonical") or {}).get("unit_number"))
            or ""
        ).strip()
        sample = {
            "source_id": str(row.get("source_id") or ""),
            "task_type": str(row.get("task_type") or ""),
            "building_type": building_type,
            "raw_address_text": raw_text,
        }

        has_strong_residential_unit_hint = bool(_STRONG_RESIDENTIAL_UNIT_HINT_RE.search(raw_text))
        is_geographic_upper_lower_only = _looks_like_geographic_upper_lower_only(raw_text)
        has_residential_like_hint = bool(_RESIDENTIAL_LIKE_HINT_RE.search(raw_text))

        if (
            building_type == "single_unit"
            and has_strong_residential_unit_hint
            and not is_geographic_upper_lower_only
        ):
            single_unit_with_strong_unit_hint.append(sample)

        if (
            building_type == "multi_unit"
            and not unit_number
            and not has_strong_residential_unit_hint
        ):
            multi_unit_without_unit_evidence.append(sample)

        if building_type == "commercial" and has_residential_like_hint:
            commercial_with_residential_pattern.append(sample)

    return {
        "single_unit_with_strong_unit_hint_count": len(single_unit_with_strong_unit_hint),
        "multi_unit_without_unit_evidence_count": len(multi_unit_without_unit_evidence),
        "commercial_with_residential_pattern_count": len(commercial_with_residential_pattern),
        "single_unit_with_strong_unit_hint_examples": single_unit_with_strong_unit_hint[:example_limit],
        "multi_unit_without_unit_evidence_examples": multi_unit_without_unit_evidence[:example_limit],
        "commercial_with_residential_pattern_examples": commercial_with_residential_pattern[:example_limit],
    }


def run_baseline_training(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    dataset_name: str = "default_training_set",
    model_name: str = "default_model",
    model_version: str = "v1",
) -> dict[str, Any]:
    run_id = create_run("ml_train", notes=f"train {model_name}:{model_version}")
    try:
        sample_rows = fetch_all(
            "SELECT COUNT(*) AS cnt FROM raw_address_record WHERE workspace_name = %s",
            (workspace_name,),
        )
        gold_rows = fetch_all(
            """
            SELECT COUNT(DISTINCT source_id) AS cnt
            FROM gold_label
            WHERE workspace_name = %s
              AND review_status = 'accepted'
              AND label_source = 'human'
            """,
            (workspace_name,),
        )
        sample_count = int(sample_rows[0]["cnt"]) if sample_rows else 0
        gold_count = int(gold_rows[0]["cnt"]) if gold_rows else 0
        workspace = get_workspace(workspace_name) or {}
        profile = str(workspace.get("default_profile") or "base_canada")
        existing_model = get_model(workspace_name, model_name, model_version)
        if existing_model and existing_model.get("default_profile"):
            profile = str(existing_model["default_profile"])
        decision_policy = _derive_decision_policy(workspace_name)
        from addressforge.learning.supervised_baseline import (
            summarize_decision_training_dataset_balance,
            train_decision_baseline
        )

        decision_label_balance = summarize_decision_training_dataset_balance(
            workspace_name,
            artifact_name=f"{model_name}_{model_version}_decision_balance",
        )
        
        # New: Train the supervised CatBoost decision model
        # 新增：训练监督式 CatBoost 决策模型
        try:
            ml_model_result = train_decision_baseline(
                workspace_name=workspace_name,
                model_name=f"{model_name}_catboost",
                model_version=model_version
            )
            # Standardize the shadow model filename for ModelService consumption
            # 为 ModelService 消费标准化影子模型文件名
            if ml_model_result.get("model_type") == "catboost":
                cb_model = ml_model_result["estimator"]
                cb_model_path = Path("runtime/models/decision_catboost_v1.cbm")
                cb_model_path.parent.mkdir(parents=True, exist_ok=True)
                cb_model.save_model(str(cb_model_path))
                logger.info("Shadow CatBoost model saved to %s", cb_model_path)
        except Exception as ml_exc:
            logger.warning("Failed to train shadow CatBoost model: %s", ml_exc)

        parser_weights = _derive_parser_weights(
            workspace_name,
            model_name=model_name,
            model_version=model_version,
            profile=profile,
            decision_policy=decision_policy,
        )
        decision_policy["parser_weights"] = parser_weights
        decision_policy["match_rule_weights"] = _derive_match_rule_weights(workspace_name)
        decision_policy["candidate_feature_weights"] = _derive_candidate_feature_weights(workspace_name)
        decision_policy["candidate_pair_weights"] = _derive_candidate_pair_weights(workspace_name)
        hard_sample_profile = _derive_hard_sample_profile(workspace_name)
        label_consistency_diagnostics = _derive_label_consistency_diagnostics(workspace_name)

        artifact_dir = _artifact_dir()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{model_name}_{model_version}_training.json"
        benchmark_summary: dict[str, Any] | None = None
        benchmark_path = Path(__file__).resolve().parents[3] / "examples" / "canada_address_benchmark.jsonl"
        if benchmark_path.exists():
            benchmark_summary = run_canada_address_benchmark(
                benchmark_path,
                workspace_name=workspace_name,
                model_name=model_name,
                model_version=model_version,
                profile=profile,
                parsers=("simple_rule", "hybrid_canada", "libpostal"),
                decision_policy=decision_policy,
            )
        artifact_payload = {
            "workspace_name": workspace_name,
            "model_name": model_name,
            "model_version": model_version,
            "model_family": ADDRESSFORGE_MODEL_FAMILY,
            "status": "trained",
            "dataset_name": dataset_name,
            "profile": profile,
            "parsers": ["simple_rule", "hybrid_canada", "libpostal"],
            "decision_policy": decision_policy,
            "training_run_id": run_id,
            "sample_count": sample_count,
            "gold_count": gold_count,
            "hard_sample_profile": hard_sample_profile,
            "label_consistency_diagnostics": label_consistency_diagnostics,
            "decision_label_balance": decision_label_balance,
            "canada_benchmark": benchmark_summary,
            "notes": "baseline training artifact with learned decision policy",
        }
        artifact_path.write_text(json.dumps(artifact_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        registry_row = register_model_version(
            workspace_name=workspace_name,
            model_name=model_name,
            model_version=model_version,
            model_family=ADDRESSFORGE_MODEL_FAMILY,
            status="trained",
            dataset_name=dataset_name,
            training_run_id=run_id,
            artifact_path=str(artifact_path),
            metrics_json={
                "training_dataset": dataset_name,
                "sample_count": sample_count,
                "gold_count": gold_count,
                "decision_policy": decision_policy,
                "hard_sample_profile": hard_sample_profile,
                "label_consistency_diagnostics": label_consistency_diagnostics,
                "decision_label_balance": decision_label_balance,
                "canada_benchmark": benchmark_summary,
            },
            notes=f"Training completed for {model_name}/{model_version} on {dataset_name}. Samples={sample_count}, Gold={gold_count}",
            is_default=int(existing_model.get("is_default") or 0) if existing_model else 0,
        )
        result = {
            "run_id": run_id,
            "workspace_name": workspace_name,
            "model_name": model_name,
            "model_version": model_version,
            "dataset_name": dataset_name,
            "sample_count": sample_count,
            "gold_count": gold_count,
            "artifact_path": str(artifact_path),
            "registry_model_id": registry_row.get("model_id"),
        }
        finish_run(run_id, "completed", notes=dumps_payload(result))
        return result
    except Exception as exc:
        finish_run(run_id, "failed", notes=dumps_payload({"error": str(exc)}))
        raise
