from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from addressforge.core.common import canonicalize_unit_number, create_run, dumps_payload, fetch_all, finish_run
from addressforge.core.config import (
    ADDRESSFORGE_MODEL_ARTIFACT_DIR,
    ADDRESSFORGE_MODEL_NAME,
    ADDRESSFORGE_MODEL_VERSION,
    ADDRESSFORGE_WORKSPACE_NAME,
)
from addressforge.core.utils import logger
from addressforge.models import get_active_model, get_model, get_workspace, register_model_version
from addressforge.learning.gold import count_gold_labels
from addressforge.learning.reporter import generate_markdown_report
from addressforge.services.model_service import build_model_service_from_manifest


@dataclass(frozen=True)
class EvaluationArtifact:
    run_id: int
    workspace_name: str
    model_name: str
    model_version: str
    dataset_name: str
    sample_count: int
    cleaned_count: int
    cleaning_coverage: float
    gold_count: int
    gold_coverage: float
    metric_name: str
    metric_value: float
    metrics_json: dict[str, Any]
    report_path: str


def _artifact_dir() -> Path:
    return Path(os.getenv("ADDRESSFORGE_MODEL_ARTIFACT_DIR", ADDRESSFORGE_MODEL_ARTIFACT_DIR)).expanduser()


def _default_canada_benchmark_path() -> Path:
    return Path(__file__).resolve().parents[3] / "examples" / "canada_address_benchmark.jsonl"


def _skip_canada_benchmark() -> bool:
    return str(os.getenv("ADDRESSFORGE_SKIP_CANADA_BENCHMARK", "0")).strip().lower() in {"1", "true", "yes"}


def _normalize_label_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _metrics_json_dict(model_row: dict[str, Any] | None) -> dict[str, Any]:
    if not model_row:
        return {}
    return _normalize_label_json(model_row.get("metrics_json"))


def _extract_gold_value(label_json: dict[str, Any], field_name: str) -> str | None:
    if field_name in {"decision", "heuristic_decision", "ml_shadow_decision", "assist_trial_decision"}:
        value = label_json.get("decision")
        if isinstance(value, str) and value.strip().lower() == "correct":
            value = "accept"
    elif field_name == "building_type":
        value = label_json.get("building_type") or label_json.get("structure_type")
    elif field_name == "unit_number":
        value = (
            label_json.get("unit_number")
            or label_json.get("suggested_unit_number")
            or (label_json.get("canonical") or {}).get("unit_number")
        )
        return canonicalize_unit_number(value) if value not in (None, "") else None
    else:
        value = label_json.get(field_name)
    if value in (None, ""):
        return None
    return str(value).strip()


def _extract_predicted_value(row: dict[str, Any], field_name: str) -> str | None:
    if field_name == "decision":
        value = row.get("decision")
    elif field_name == "heuristic_decision":
        value = row.get("heuristic_decision")
    elif field_name == "ml_shadow_decision":
        value = row.get("ml_shadow_decision")
    elif field_name == "building_type":
        value = row.get("building_type")
    elif field_name == "ml_building_type":
        # Phase 17: Support ML BuildingType extraction
        # 第 17 阶段：支持 ML BuildingType 提取
        value = row.get("ml_building_type")
    elif field_name == "unit_number":
        value = canonicalize_unit_number(row.get("suggested_unit_number"))
    else:
        value = row.get(field_name)
    if value in (None, ""):
        return None
    return str(value).strip()


def _field_metrics(rows: list[dict[str, Any]], field_name: str) -> dict[str, Any]:
    total = 0
    exact_matches = 0
    tp = 0
    fp = 0
    fn = 0
    skipped = 0
    for row in rows:
        gold = _extract_gold_value(_normalize_label_json(row.get("label_json")), field_name)
        if gold is None:
            skipped += 1
            continue
        pred = _extract_predicted_value(row, field_name)
        total += 1
        if pred == gold:
            exact_matches += 1
            tp += 1
        else:
            if pred is not None:
                fp += 1
            fn += 1
    accuracy = 0.0 if total <= 0 else round(exact_matches / total, 4)
    precision = 0.0 if (tp + fp) <= 0 else round(tp / (tp + fp), 4)
    recall = 0.0 if (tp + fn) <= 0 else round(tp / (tp + fn), 4)
    f1 = 0.0 if (precision + recall) <= 0 else round((2 * precision * recall) / (precision + recall), 4)
    return {
        "field": field_name,
        "total": total,
        "skipped": skipped,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _positive_label_metrics(rows: list[dict[str, Any]], field_name: str, positive_label: str) -> dict[str, Any]:
    total = 0
    tp = 0
    fp = 0
    fn = 0
    tn = 0
    skipped = 0
    for row in rows:
        gold = _extract_gold_value(_normalize_label_json(row.get("label_json")), field_name)
        if gold is None:
            skipped += 1
            continue
        pred = _extract_predicted_value(row, field_name)
        total += 1
        gold_pos = gold == positive_label
        pred_pos = pred == positive_label
        if gold_pos and pred_pos:
            tp += 1
        elif not gold_pos and pred_pos:
            fp += 1
        elif gold_pos and not pred_pos:
            fn += 1
        else:
            tn += 1
    accuracy = 0.0 if total <= 0 else round((tp + tn) / total, 4)
    precision = 0.0 if (tp + fp) <= 0 else round(tp / (tp + fp), 4)
    recall = 0.0 if (tp + fn) <= 0 else round(tp / (tp + fn), 4)
    f1 = 0.0 if (precision + recall) <= 0 else round((2 * precision * recall) / (precision + recall), 4)
    return {
        "field": field_name,
        "positive_label": positive_label,
        "total": total,
        "skipped": skipped,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _categorize_error(gold_row: dict[str, Any], pred_row: dict[str, Any], field_name: str) -> str:
    gold = _extract_gold_value(_normalize_label_json(gold_row.get("label_json")), field_name)
    pred = _extract_predicted_value(pred_row, field_name)
    
    # 获取原始文本和解析上下文
    raw_text = str(pred_row.get("raw_address_text") or "").upper()
    unit_source = pred_row.get("unit_source") or "unknown"

    if field_name == "unit_number":
        if gold and not pred:
            if any(k in raw_text for k in ["#", "UNIT", "APT", "SUITE"]):
                return "UNIT_PATTERN_MISS" # 文本中有关键字但没解析出来
            return "REFERENCE_MISSING_UNIT" # 文本中无关键字，参考库也未命中
        if gold and pred and gold != pred:
            if unit_source == "simple_fallback":
                return "UNIT_NORMALIZATION_ERROR"
            return "UNIT_PARSING_CONFLICT"
            
    if field_name == "building_type":
        if gold == "commercial" and pred != "commercial":
            return "COMMERCIAL_IDENTIFICATION_FAILURE"
        if gold == "multi_unit" and pred == "single_unit":
            return "MULTI_UNIT_UNDER_COUNT"
        return "WRONG_BUILDING_TYPE"
        
    if field_name == "decision":
        if gold == "accept" and pred == "review":
            return "OVER_SENSITIVE_REVIEW" # 系统太敏感，人工认为没问题
        if gold == "review" and pred == "accept":
            return "UNDETECTED_CONFLICT" # 系统漏掉了冲突
            
    return "GENERAL_MISMATCH"

def _field_error_samples(rows: list[dict[str, Any]], field_name: str, limit: int = 100) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for row in rows:
        gold = _extract_gold_value(_normalize_label_json(row.get("label_json")), field_name)
        if gold is None:
            continue
        pred = _extract_predicted_value(row, field_name)
        if pred == gold:
            continue
        samples.append(
            {
                "source_id": row.get("source_id"),
                "raw_text": row.get("raw_address_text"),
                "task_type": row.get("task_type"),
                "field": field_name,
                "gold": gold,
                "predicted": pred,
                "bucket": _categorize_error(row, row, field_name),
            }
        )
        if len(samples) >= limit:
            break
    return samples


def _generate_bucket_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    bucket_counts: dict[str, int] = {}
    for sample in samples:
        bucket = str(sample.get("bucket") or "GENERAL_MISMATCH")
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    ordered = sorted(bucket_counts.items(), key=lambda item: (-item[1], item[0]))
    return {
        "total_errors": len(samples),
        "bucket_counts": dict(ordered),
        "top_buckets": [{"bucket": bucket, "count": count} for bucket, count in ordered[:10]],
    }


def _categorize_shadow_disagreement(row: dict[str, Any]) -> str:
    heuristic = _extract_predicted_value(row, "heuristic_decision") or "unknown"
    model = _extract_predicted_value(row, "ml_shadow_decision") or "unknown"
    if heuristic == model:
        return "AGREE"
    if heuristic == "accept" and model == "review":
        return "MODEL_MORE_CONSERVATIVE_REVIEW"
    if heuristic == "review" and model == "accept":
        return "MODEL_MORE_AGGRESSIVE_ACCEPT"
    if model == "reject" and heuristic != "reject":
        return "MODEL_REJECT_ESCALATION"
    if heuristic == "reject" and model != "reject":
        return "MODEL_REJECT_RECOVERY"
    return "GENERAL_DISAGREEMENT"


def _decision_shadow_assist_summary(rows: list[dict[str, Any]], limit: int = 50) -> dict[str, Any]:
    heuristic_metrics = _field_metrics(rows, "heuristic_decision") if rows else None
    model_metrics = _field_metrics(rows, "ml_shadow_decision") if rows else None
    assist_trial_rows: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    bucket_counts: dict[str, int] = {}
    assist_guard_counts: dict[str, int] = {}
    assist_recommended_counts: dict[str, int] = {}
    compared = 0
    disagreed = 0
    model_available = 0
    assist_eligible = 0
    assist_compared = 0
    assist_gold_matches = 0
    for row in rows:
        heuristic = _extract_predicted_value(row, "heuristic_decision")
        model = _extract_predicted_value(row, "ml_shadow_decision")
        gold = _extract_gold_value(_normalize_label_json(row.get("label_json")), "decision")
        assist_recommended_decision = _extract_predicted_value(row, "assist_recommended_decision")
        assist_guard_reason = str(row.get("assist_guard_reason") or "unknown")
        assist_is_eligible = bool(row.get("assist_eligible"))
        if heuristic is None:
            continue
        assist_trial_decision = (
            assist_recommended_decision
            if assist_is_eligible and assist_recommended_decision is not None
            else heuristic
        )
        assist_trial_rows.append(
            {
                **row,
                "assist_trial_decision": assist_trial_decision,
            }
        )
        compared += 1
        if model is not None:
            model_available += 1
        if assist_is_eligible:
            assist_eligible += 1
            assist_guard_counts[assist_guard_reason] = assist_guard_counts.get(assist_guard_reason, 0) + 1
            if assist_recommended_decision is not None:
                assist_recommended_counts[assist_recommended_decision] = assist_recommended_counts.get(assist_recommended_decision, 0) + 1
                if gold is not None:
                    assist_compared += 1
                    if assist_recommended_decision == gold:
                        assist_gold_matches += 1
        if heuristic == model:
            continue
        disagreed += 1
        bucket = _categorize_shadow_disagreement(row)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        if len(disagreements) < limit:
            disagreements.append(
                {
                    "source_id": row.get("source_id"),
                    "raw_text": row.get("raw_address_text"),
                    "gold": _extract_gold_value(_normalize_label_json(row.get("label_json")), "decision"),
                    "heuristic": heuristic,
                    "model": model,
                    "bucket": bucket,
                    "model_score": row.get("ml_shadow_score"),
                    "model_status": row.get("ml_shadow_status"),
                    "disagreement_reason": row.get("shadow_disagreement_reason"),
                    "assist_eligible": assist_is_eligible,
                    "assist_recommended_decision": assist_recommended_decision,
                    "assist_guard_reason": assist_guard_reason,
                }
            )
    ordered_buckets = sorted(bucket_counts.items(), key=lambda item: (-item[1], item[0]))
    ordered_assist_guards = sorted(assist_guard_counts.items(), key=lambda item: (-item[1], item[0]))
    heuristic_f1 = float((heuristic_metrics or {}).get("f1") or 0.0)
    model_f1 = float((model_metrics or {}).get("f1") or 0.0)
    assist_trial_metrics = _field_metrics(assist_trial_rows, "assist_trial_decision") if assist_trial_rows else None
    assist_trial_f1 = float((assist_trial_metrics or {}).get("f1") or 0.0)
    return {
        "heuristic": heuristic_metrics,
        "ml_shadow": model_metrics,
        "assist_trial": assist_trial_metrics,
        "compared": compared,
        "model_available": model_available,
        "disagreement_rate": round(disagreed / compared, 4) if compared else 0.0,
        "shadow_advantage": round(model_f1 - heuristic_f1, 4),
        "assist_trial_advantage": round(assist_trial_f1 - heuristic_f1, 4),
        "bucket_counts": dict(ordered_buckets),
        "top_buckets": [{"bucket": bucket, "count": count} for bucket, count in ordered_buckets[:10]],
        "assist_readiness": {
            "eligible_count": assist_eligible,
            "recommended_decision_counts": assist_recommended_counts,
            "guard_reason_counts": dict(ordered_assist_guards),
            "gold_compared": assist_compared,
            "gold_match_rate": round(assist_gold_matches / assist_compared, 4) if assist_compared else 0.0,
        },
        "disagreement_samples": disagreements,
    }


def _decision_assist_rollout_readiness(shadow_summary: dict[str, Any] | None) -> dict[str, Any]:
    shadow_summary = shadow_summary if isinstance(shadow_summary, dict) else {}
    heuristic = shadow_summary.get("heuristic") or {}
    ml_shadow = shadow_summary.get("ml_shadow") or {}
    assist_trial = shadow_summary.get("assist_trial") or {}
    assist = shadow_summary.get("assist_readiness") or {}

    heuristic_f1 = float(heuristic.get("f1") or 0.0)
    shadow_f1 = float(ml_shadow.get("f1") or 0.0)
    assist_trial_f1 = float(assist_trial.get("f1") or 0.0)
    shadow_advantage = float(shadow_summary.get("shadow_advantage") or 0.0)
    assist_trial_advantage = float(shadow_summary.get("assist_trial_advantage") or 0.0)
    disagreement_rate = float(shadow_summary.get("disagreement_rate") or 0.0)
    eligible_count = int(assist.get("eligible_count") or 0)
    gold_match_rate = float(assist.get("gold_match_rate") or 0.0)
    gold_compared = int(assist.get("gold_compared") or 0)

    checks = {
        "shadow_beats_heuristic": shadow_f1 > heuristic_f1 and shadow_advantage > 0.0,
        "assist_trial_not_worse_than_shadow": assist_trial_f1 >= shadow_f1,
        "disagreement_rate_safe": disagreement_rate <= 0.15,
        "eligible_sample_count_sufficient": eligible_count >= 10,
        "assist_gold_match_rate_sufficient": gold_compared >= 5 and gold_match_rate >= 0.80,
    }
    passed = all(checks.values())
    if passed:
        status = "ready_for_assist_trial"
    elif checks["shadow_beats_heuristic"] and checks["disagreement_rate_safe"]:
        status = "needs_more_assist_calibration"
    else:
        status = "shadow_only"

    # Phase 18: Standardize contract for Release Gate 2.0
    # 第 18 阶段：标准化 Release Gate 2.0 的契约
    return {
        "status": status,
        "promote_recommended": bool(status == "ready_for_assist_trial"),
        "checks": checks,
        "heuristic_f1": round(heuristic_f1, 4),
        "ml_shadow_f1": round(shadow_f1, 4),
        "assist_trial_f1": round(assist_trial_f1, 4),
        "shadow_advantage": round(shadow_advantage, 4),
        "assist_trial_advantage": round(assist_trial_advantage, 4),
        "disagreement_rate": round(disagreement_rate, 4),
        "eligible_count": eligible_count,
        "assist_gold_compared": gold_compared,
        "assist_gold_match_rate": round(gold_match_rate, 4),
    }


def _building_type_assist_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    compared = 0
    eligible_count = 0
    applied_count = 0
    gold_match_count = 0
    transition_counts: dict[str, int] = {}
    eligible_transition_counts: dict[str, int] = {}
    applied_transition_counts: dict[str, int] = {}
    samples: list[dict[str, Any]] = []

    for row in rows:
        gold_value = _extract_gold_value(_normalize_label_json(row.get("label_json")), "building_type")
        if gold_value in (None, ""):
            continue
        compared += 1
        heuristic_value = _extract_predicted_value(row, "building_type")
        ml_value = _extract_predicted_value(row, "ml_building_type")
        if not ml_value or ml_value == heuristic_value:
            continue
        transition = f"{heuristic_value or 'unknown'}->{ml_value}"
        transition_counts[transition] = transition_counts.get(transition, 0) + 1
        confidence = _to_float(row.get("bt_confidence"))
        assist_enabled = bool(row.get("bt_assist_enabled"))
        policy_mode = str(row.get("assist_policy_mode") or "").strip().lower()
        allowed_transitions = row.get("bt_allowed_transitions") or []
        is_allowed = [heuristic_value, ml_value] in allowed_transitions
        is_eligible = assist_enabled and policy_mode == "assist_trial" and is_allowed and confidence >= 0.90
        if is_eligible:
            eligible_count += 1
            eligible_transition_counts[transition] = eligible_transition_counts.get(transition, 0) + 1
        was_applied = bool(row.get("bt_override_applied"))
        if was_applied:
            applied_count += 1
            applied_transition_counts[transition] = applied_transition_counts.get(transition, 0) + 1
            if ml_value == gold_value:
                gold_match_count += 1
        if len(samples) < 10:
            samples.append(
                {
                    "source_id": row.get("source_id"),
                    "raw_address_text": row.get("raw_address_text"),
                    "heuristic_building_type": heuristic_value,
                    "ml_building_type": ml_value,
                    "gold_building_type": gold_value,
                    "bt_confidence": confidence,
                    "assist_eligible": is_eligible,
                    "bt_override_applied": was_applied,
                    "transition": transition,
                }
            )

    return {
        "compared": compared,
        "eligible_count": eligible_count,
        "applied_count": applied_count,
        "gold_match_rate": round((gold_match_count / applied_count), 4) if applied_count > 0 else 0.0,
        "transition_counts": transition_counts,
        "eligible_transition_counts": eligible_transition_counts,
        "applied_transition_counts": applied_transition_counts,
        "samples": samples,
    }


def _decision_threshold_tuning_hints(
    shadow_summary: dict[str, Any] | None,
    readiness: dict[str, Any] | None,
) -> dict[str, Any]:
    shadow_summary = shadow_summary if isinstance(shadow_summary, dict) else {}
    readiness = readiness if isinstance(readiness, dict) else {}
    bucket_counts = shadow_summary.get("bucket_counts") or {}
    assist = shadow_summary.get("assist_readiness") or {}
    guard_reason_counts = assist.get("guard_reason_counts") or {}

    hints: list[dict[str, Any]] = []
    if int(bucket_counts.get("MODEL_MORE_AGGRESSIVE_ACCEPT") or 0) > 0:
        hints.append(
            {
                "priority": "high",
                "target_bucket": "MODEL_MORE_AGGRESSIVE_ACCEPT",
                "policy_area": "assist_accept",
                "suggestion": "tighten accept-recovery assist thresholds or expand parser/reference safety guards before enabling assist.",
                "candidate_thresholds": [
                    "assist_accept_score_threshold",
                    "assist_accept_parse_score_threshold",
                ],
            }
        )
    if int(bucket_counts.get("MODEL_MORE_CONSERVATIVE_REVIEW") or 0) > 0:
        hints.append(
            {
                "priority": "high",
                "target_bucket": "MODEL_MORE_CONSERVATIVE_REVIEW",
                "policy_area": "assist_review",
                "suggestion": "tighten review-escalation assist eligibility so only disagreement cases with real guard triggers are surfaced.",
                "candidate_thresholds": [
                    "assist_review_score_threshold",
                    "assist_review_parse_score_threshold",
                    "assist_review_reference_score_threshold",
                ],
            }
        )
    if int(bucket_counts.get("MODEL_REJECT_ESCALATION") or 0) > 0:
        hints.append(
            {
                "priority": "medium",
                "target_bucket": "MODEL_REJECT_ESCALATION",
                "policy_area": "reject_override",
                "suggestion": "keep reject override disabled until explicit reject calibration and minority-label evidence improves.",
                "candidate_thresholds": [],
            }
        )
    if int(guard_reason_counts.get("parser_disagreement_guard") or 0) > 0:
        hints.append(
            {
                "priority": "medium",
                "target_bucket": "PARSER_DISAGREEMENT_GUARD",
                "policy_area": "guard_coverage",
                "suggestion": "parser disagreement is still blocking assist candidates; improve parser recovery before relaxing review boundaries.",
                "candidate_thresholds": [],
            }
        )

    overall_status = str(readiness.get("status") or "shadow_only")
    next_action = (
        "hold shadow-only and continue boundary calibration"
        if overall_status != "ready_for_assist_trial"
        else "prepare a narrow assist trial on guarded accept/review transitions"
    )
    return {
        "status": overall_status,
        "next_action": next_action,
        "hints": hints,
    }


def _decision_policy_calibration_proposal(
    tuning_hints: dict[str, Any] | None,
    readiness: dict[str, Any] | None,
) -> dict[str, Any]:
    tuning_hints = tuning_hints if isinstance(tuning_hints, dict) else {}
    readiness = readiness if isinstance(readiness, dict) else {}
    changes: list[dict[str, Any]] = []

    for hint in tuning_hints.get("hints") or []:
        bucket = str(hint.get("target_bucket") or "")
        if bucket == "MODEL_MORE_AGGRESSIVE_ACCEPT":
            # Separate accept and enrich recovery tuning
            # 分开处理 accept 和 enrich 恢复的调优
            changes.extend(
                [
                    {
                        "threshold": "assist_accept_score_threshold",
                        "direction": "increase",
                        "step": 0.02,
                        "reason": "reduce aggressive accept recoveries",
                    },
                    {
                        "threshold": "assist_accept_parse_score_threshold",
                        "direction": "increase",
                        "step": 0.02,
                        "reason": "require stronger parse quality for accept recovery",
                    },
                ]
            )
        elif bucket == "MODEL_MORE_CONSERVATIVE_REVIEW":
            # Review escalation tuning
            # Review 升级调优
            changes.extend(
                [
                    {
                        "threshold": "assist_review_score_threshold",
                        "direction": "increase",
                        "step": 0.02,
                        "reason": "only allow review escalation when the model is more certain",
                    },
                    {
                        "threshold": "assist_review_parse_score_threshold",
                        "direction": "decrease",
                        "step": 0.02,
                        "reason": "narrow review escalation scope",
                    },
                    {
                        "threshold": "assist_review_reference_score_threshold",
                        "direction": "increase",
                        "step": 0.02,
                        "reason": "stricter reference requirement for review escalation",
                    },
                ]
            )
        elif bucket == "MODEL_REJECT_ESCALATION":
            changes.append(
                {
                    "threshold": "reject_override",
                    "direction": "hold_disabled",
                    "step": 0.0,
                    "reason": "reject override should remain disabled until stronger minority-label evidence exists",
                }
            )

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in changes:
        key = (str(item.get("threshold")), str(item.get("direction")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    readiness_status = str(readiness.get("status") or "shadow_only")
    return {
        "status": readiness_status,
        "recommended_changes": deduped,
        "apply_now": False,
        "reason": "shadow-only calibration proposal; apply manually after validating on the next evaluation cycle",
    }


def _load_gold_comparison_rows(workspace_name: str) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT
            g.gold_label_id,
            g.source_id,
            g.task_type,
            g.label_json,
            r.raw_address_text,
            r.city,
            r.province,
            r.postal_code,
            r.country_code,
            acr.decision,
            acr.building_type,
            acr.suggested_unit_number
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
        LEFT JOIN address_cleaning_result acr
          ON acr.workspace_name = g.workspace_name
         AND acr.raw_id = r.raw_id
        WHERE g.workspace_name = %s
          AND g.review_status = 'accepted'
          AND g.label_source = 'human'
        ORDER BY g.gold_label_id ASC
        """,
        (workspace_name, workspace_name),
    )


def _resolve_model_runtime(
    workspace_name: str,
    model_name: str,
    model_version: str,
) -> tuple[str, tuple[str, ...], dict[str, Any] | None, Any]:
    workspace = get_workspace(workspace_name) or {}
    target_model = get_model(workspace_name, model_name, model_version) or {}
    metrics_json = _metrics_json_dict(target_model)
    target_profile = (
        target_model.get("default_profile")
        or workspace.get("default_profile")
        or "base_canada"
    )
    target_parsers: tuple[str, ...] = ("simple_rule", "hybrid_canada", "libpostal")
    target_decision_policy: dict[str, Any] | None = None
    decision_model_artifact: dict[str, Any] = {}
    runtime_binding = metrics_json.get("runtime_binding") if isinstance(metrics_json.get("runtime_binding"), dict) else {}
    if runtime_binding:
        runtime_profile = runtime_binding.get("profile")
        runtime_parsers = runtime_binding.get("parsers")
        runtime_policy = runtime_binding.get("decision_policy")
        if isinstance(runtime_profile, str) and runtime_profile.strip():
            target_profile = runtime_profile.strip()
        if isinstance(runtime_parsers, list) and runtime_parsers:
            target_parsers = tuple(str(item) for item in runtime_parsers if str(item).strip())
        if isinstance(runtime_policy, dict):
            target_decision_policy = runtime_policy
    # Extract manifests for sub-services
    # 提取子服务的清单
    decision_model_artifact = (
        metrics_json.get("decision_model_artifact")
        if isinstance(metrics_json.get("decision_model_artifact"), dict)
        else {}
    )
    reranker_model_artifact = (
        metrics_json.get("reranker_model_artifact")
        if isinstance(metrics_json.get("reranker_model_artifact"), dict)
        else {}
    )
    building_type_model_artifact = (
        metrics_json.get("building_type_model_artifact")
        if isinstance(metrics_json.get("building_type_model_artifact"), dict)
        else {}
    )

    target_artifact_path = target_model.get("artifact_path")
    artifact_payload = {}
    if target_artifact_path:
        try:
            artifact_payload = json.loads(Path(target_artifact_path).read_text(encoding="utf-8"))
            artifact_profile = artifact_payload.get("profile")
            artifact_parsers = artifact_payload.get("parsers")
            artifact_decision_policy = artifact_payload.get("decision_policy")
            if isinstance(artifact_profile, str) and artifact_profile.strip():
                target_profile = artifact_profile.strip()
            if isinstance(artifact_parsers, list) and artifact_parsers:
                target_parsers = tuple(str(item) for item in artifact_parsers if str(item).strip())
            if isinstance(artifact_decision_policy, dict):
                target_decision_policy = artifact_decision_policy
            
            # Fill missing artifacts from artifact file
            if not decision_model_artifact and isinstance(artifact_payload.get("decision_model_artifact"), dict):
                decision_model_artifact = artifact_payload["decision_model_artifact"]
            if not reranker_model_artifact and isinstance(artifact_payload.get("reranker_model_artifact"), dict):
                reranker_model_artifact = artifact_payload["reranker_model_artifact"]
            if not building_type_model_artifact and isinstance(artifact_payload.get("building_type_model_artifact"), dict):
                building_type_model_artifact = artifact_payload["building_type_model_artifact"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load target model artifact for runtime binding: %s", exc)
            
    # Build unified manifest
    full_manifest = {
        **artifact_payload,
        "decision_model_artifact": decision_model_artifact,
        "reranker_model_artifact": reranker_model_artifact,
        "building_type_model_artifact": building_type_model_artifact
    }
    
    from addressforge.services.model_service import build_model_service_from_manifest
    from addressforge.services.reranker_service import build_reranker_service_from_manifest
    
    return {
        "profile": target_profile,
        "parsers": target_parsers,
        "decision_policy": target_decision_policy,
        "model_service": build_model_service_from_manifest(full_manifest),
        "reranker_service": build_reranker_service_from_manifest(full_manifest),
        "manifest": full_manifest
    }


def _predict_gold_rows_with_runtime(
    workspace_name: str,
    model_name: str,
    model_version: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not rows:
        return rows
    from addressforge.api.server import AddressPlatformService, AddressRequest

    target_runtime = _resolve_model_runtime(
        workspace_name,
        model_name,
        model_version,
    )
    service = AddressPlatformService(
        default_profile=target_runtime["profile"],
        default_parsers=target_runtime["parsers"],
        decision_policy=target_runtime["decision_policy"],
        model_service=target_runtime["model_service"],
        reranker_service=target_runtime["reranker_service"],
    )
    predicted_rows: list[dict[str, Any]] = []
    for row in rows:
        current = dict(row)
        raw_text = row.get("raw_address_text")
        if raw_text:
            try:
                result = service.validate(
                    AddressRequest(
                        raw_address_text=str(raw_text),
                        city=row.get("city"),
                        province=row.get("province"),
                        postal_code=row.get("postal_code"),
                        country_code=str(row.get("country_code") or "CA"),
                        profile=target_runtime["profile"],
                        parsers=list(target_runtime["parsers"]),
                        reranker_version=model_version,
                    )
                )
                current["decision"] = result.get("decision")
                current["heuristic_decision"] = result.get("decision")
                current["building_type"] = result.get("building_type")
                current["suggested_unit_number"] = result.get("suggested_unit_number")
                ml_shadow = result.get("ml_decision") if isinstance(result.get("ml_decision"), dict) else {}
                shadow_assist = result.get("shadow_assist") if isinstance(result.get("shadow_assist"), dict) else {}
                current["ml_shadow_decision"] = ml_shadow.get("ml_decision")
                current["ml_shadow_score"] = ml_shadow.get("ml_score")
                current["ml_shadow_status"] = ml_shadow.get("status")
                
                # Phase 17: Extract ML BuildingType
                # 第 17 阶段：提取 ML 建筑类型
                current["ml_building_type"] = shadow_assist.get("ml_building_type")
                current["bt_confidence"] = shadow_assist.get("bt_confidence")
                current["bt_assist_enabled"] = shadow_assist.get("bt_assist_enabled")
                current["bt_allowed_transitions"] = shadow_assist.get("bt_allowed_transitions")
                current["bt_override_applied"] = shadow_assist.get("bt_override_applied")
                current["assist_policy_mode"] = shadow_assist.get("assist_policy_mode")
                current["reranker_impact_detected"] = shadow_assist.get("reranker_impact_detected", False)
                
                # New: Detailed Reranker impact tracking
                # 新增：详细的重排器影响跟踪
                if current["reranker_impact_detected"]:
                    parser_result = result.get("parser_result") or {}
                    candidates = parser_result.get("candidates") or []
                    if candidates:
                        h_best = max(candidates, key=lambda x: x.get("score") or 0)
                        m_best = parser_result.get("best_candidate") or {}
                        current["reranker_impact_detail"] = {
                            "heuristic_best_parser": h_best.get("parser_name"),
                            "ml_best_parser": m_best.get("parser_name"),
                            "h_key": h_best.get("parsed", {}).get("full_address_key"),
                            "m_key": m_best.get("parsed", {}).get("full_address_key")
                        }
                
                current["shadow_disagreement_reason"] = shadow_assist.get("disagreement_reason")
                current["assist_eligible"] = shadow_assist.get("assist_eligible")
                current["assist_recommended_decision"] = shadow_assist.get("assist_recommended_decision")
                current["assist_guard_reason"] = shadow_assist.get("assist_guard_reason")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Runtime gold prediction failed for source_id=%s: %s", row.get("source_id"), exc)
                current["decision"] = None
                current["heuristic_decision"] = None
                current["building_type"] = None
                current["suggested_unit_number"] = None
                current["ml_shadow_decision"] = None
                current["ml_shadow_score"] = None
                current["ml_shadow_status"] = "error"
                current["ml_building_type"] = None
                current["bt_confidence"] = None
                current["bt_assist_enabled"] = False
                current["bt_allowed_transitions"] = []
                current["bt_override_applied"] = False
                current["assist_policy_mode"] = None
                current["reranker_impact_detected"] = False
                current["shadow_disagreement_reason"] = "runtime_error"
                current["assist_eligible"] = False
                current["assist_recommended_decision"] = None
                current["assist_guard_reason"] = "runtime_error"
        predicted_rows.append(current)
    return predicted_rows


def _load_cleaning_distribution(workspace_name: str) -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT decision, building_type, suggested_unit_number
        FROM address_cleaning_result
        WHERE workspace_name = %s
        """,
        (workspace_name,),
    )
    total = len(rows)
    decision_counts = {"accept": 0, "review": 0, "reject": 0, "enrich": 0}
    building_counts = {"single_unit": 0, "multi_unit": 0, "commercial": 0, "unknown": 0}
    with_unit = 0
    for row in rows:
        decision = str(row.get("decision") or "").strip().lower()
        building = str(row.get("building_type") or "").strip().lower()
        if decision in decision_counts:
            decision_counts[decision] += 1
        if building in building_counts:
            building_counts[building] += 1
        if row.get("suggested_unit_number") not in (None, ""):
            with_unit += 1
    def _rate(count: int) -> float:
        return 0.0 if total <= 0 else round(count / total, 4)
    return {
        "total": total,
        "decision_counts": decision_counts,
        "building_type_counts": building_counts,
        "accept_rate": _rate(decision_counts["accept"]),
        "review_rate": _rate(decision_counts["review"]),
        "reject_rate": _rate(decision_counts["reject"]),
        "enrich_rate": _rate(decision_counts["enrich"]),
        "commercial_detection_rate": _rate(building_counts["commercial"]),
        "unit_coverage": _rate(with_unit),
    }


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _compare_release_benchmark(candidate: dict[str, Any], active: dict[str, Any] | None) -> dict[str, Any]:
    if not active:
        return {
            "active_available": False,
            "candidate_only": True,
            "promote_recommended": True,
            "gate_checks": [],
        }
    checks = [
        ("decision_f1", "min"),
        ("building_type_f1", "min"),
        ("unit_number_f1", "min"),
        ("unit_recall", "min"),
        ("commercial_f1", "min"),
        ("review_rate", "max"),
        ("reject_rate", "max"),
    ]
    gate_checks: list[dict[str, Any]] = []
    promote_recommended = True
    for metric_name, rule in checks:
        cand = _to_float(candidate.get(metric_name))
        act = _to_float(active.get(metric_name))
        if rule == "min":
            passed = cand >= act
        else:
            passed = cand <= act
        if not passed:
            promote_recommended = False
        gate_checks.append(
            {
                "metric": metric_name,
                "rule": rule,
                "candidate": cand,
                "active": act,
                "delta": round(cand - act, 4),
                "passed": passed,
            }
        )
    return {
        "active_available": True,
        "candidate_only": False,
        "promote_recommended": promote_recommended,
        "gate_checks": gate_checks,
    }


def _build_release_benchmark(
    decision_metrics: dict[str, Any] | None,
    building_metrics: dict[str, Any] | None,
    unit_metrics: dict[str, Any] | None,
    commercial_metrics: dict[str, Any] | None,
    cleaning_distribution: dict[str, Any],
) -> dict[str, Any]:
    return {
        "decision_f1": _to_float((decision_metrics or {}).get("f1")),
        "building_type_f1": _to_float((building_metrics or {}).get("f1")),
        "unit_number_f1": _to_float((unit_metrics or {}).get("f1")),
        "unit_recall": _to_float((unit_metrics or {}).get("recall")),
        "commercial_f1": _to_float((commercial_metrics or {}).get("f1")),
        "accept_rate": _to_float(cleaning_distribution.get("accept_rate")),
        "review_rate": _to_float(cleaning_distribution.get("review_rate")),
        "reject_rate": _to_float(cleaning_distribution.get("reject_rate")),
    }


def run_baseline_evaluation(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    model_name: str = ADDRESSFORGE_MODEL_NAME,
    model_version: str = ADDRESSFORGE_MODEL_VERSION,
    dataset_name: str = "default_training_set",
) -> dict[str, Any]:
    run_id = create_run("ml_eval", notes=f"evaluate model={model_name} dataset={dataset_name}")
    try:
        samples = fetch_all(
            "SELECT COUNT(*) AS cnt FROM raw_address_record WHERE workspace_name = %s",
            (workspace_name,),
        )
        gold_count = count_gold_labels(workspace_name, review_status="accepted", label_source="human")
        cleaned = fetch_all(
            "SELECT COUNT(*) AS cnt FROM address_cleaning_result WHERE workspace_name = %s",
            (workspace_name,),
        )
        sample_count = int(samples[0]["cnt"]) if samples else 0
        cleaned_count = int(cleaned[0]["cnt"]) if cleaned else 0
        cleaning_coverage = 0.0 if sample_count <= 0 else round(min(0.99, cleaned_count / sample_count), 4)
        gold_coverage = 0.0 if sample_count <= 0 else round(min(0.99, gold_count / sample_count), 4)
        gold_rows = _load_gold_comparison_rows(workspace_name) if gold_count > 0 else []
        if gold_rows:
            gold_rows = _predict_gold_rows_with_runtime(workspace_name, model_name, model_version, gold_rows)
        decision_metrics = _field_metrics(gold_rows, "decision") if gold_rows else None
        building_metrics = _field_metrics(gold_rows, "building_type") if gold_rows else None
        unit_metrics = _field_metrics(gold_rows, "unit_number") if gold_rows else None
        commercial_metrics = _positive_label_metrics(gold_rows, "building_type", "commercial") if gold_rows else None
        cleaning_distribution = _load_cleaning_distribution(workspace_name)
        metrics_json: dict[str, Any] = {
            "cleaning_coverage": cleaning_coverage,
            "gold_coverage": gold_coverage,
            "sample_count": sample_count,
            "cleaned_count": cleaned_count,
            "gold_count": gold_count,
            "runtime_distribution": cleaning_distribution,
        }
        metrics_json["release_benchmark"] = _build_release_benchmark(
            decision_metrics,
            building_metrics,
            unit_metrics,
            commercial_metrics,
            cleaning_distribution,
        )
        if decision_metrics:
            metrics_json["decision"] = decision_metrics
            errors = _field_error_samples(gold_rows, "decision")
            metrics_json["decision_errors"] = errors
            metrics_json["decision_error_buckets"] = _generate_bucket_summary(errors)
            metrics_json["decision_shadow_assist"] = _decision_shadow_assist_summary(gold_rows)
            metrics_json["decision_assist_rollout_readiness"] = _decision_assist_rollout_readiness(
                metrics_json["decision_shadow_assist"]
            )
            metrics_json["decision_threshold_tuning_hints"] = _decision_threshold_tuning_hints(
                metrics_json["decision_shadow_assist"],
                metrics_json["decision_assist_rollout_readiness"],
            )
            metrics_json["decision_policy_calibration_proposal"] = _decision_policy_calibration_proposal(
                metrics_json["decision_threshold_tuning_hints"],
                metrics_json["decision_assist_rollout_readiness"],
            )
        if building_metrics:
            metrics_json["building_type"] = building_metrics
            errors = _field_error_samples(gold_rows, "building_type")
            metrics_json["building_type_errors"] = errors
            metrics_json["building_type_error_buckets"] = _generate_bucket_summary(errors)
            
            # Phase 17: Evaluate ML BuildingType
            # 第 17 阶段：评估 ML BuildingType
            ml_building_metrics = _field_metrics(gold_rows, "ml_building_type") if gold_rows else None
            metrics_json["building_type_shadow_assist"] = {
                "heuristic": building_metrics,
                "ml_shadow": ml_building_metrics,
                "shadow_advantage": float(ml_building_metrics.get("f1", 0.0)) - float(building_metrics.get("f1", 0.0)) if ml_building_metrics and building_metrics else 0.0,
                "assist_summary": _building_type_assist_summary(gold_rows),
            }
        if unit_metrics:
            metrics_json["unit_number"] = unit_metrics
            errors = _field_error_samples(gold_rows, "unit_number")
            metrics_json["unit_number_errors"] = errors
            metrics_json["unit_number_error_buckets"] = _generate_bucket_summary(errors)
        if commercial_metrics:
            metrics_json["commercial"] = commercial_metrics
        benchmark_path = _default_canada_benchmark_path()
        if benchmark_path.exists() and not _skip_canada_benchmark():
            try:
                from addressforge.learning.canada_benchmark import run_canada_address_benchmark
                target_runtime = _resolve_model_runtime(
                    workspace_name,
                    model_name,
                    model_version,
                )
                metrics_json["canada_benchmark"] = run_canada_address_benchmark(
                    benchmark_path,
                    workspace_name=workspace_name,
                    model_name=model_name,
                    model_version=model_version,
                    profile=target_runtime["profile"],
                    parsers=target_runtime["parsers"],
                    decision_policy=target_runtime["decision_policy"],
                    reranker_service=target_runtime["reranker_service"],
                    model_service=target_runtime["model_service"],
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Canada benchmark evaluation failed: %s", exc)
        # 5. Integration: Historical Replay & Consistency Check
        # 5. 集成：历史重放与一致性检查
        replay_result: dict[str, Any] | None = None
        replay_error: str | None = None
        skip_replay = str(os.getenv("ADDRESSFORGE_SKIP_REPLAY_ON_EVAL", "0")).strip().lower() in {"1", "true", "yes"}
        if skip_replay:
            replay_error = "skipped_by_config"
            logger.info("Skipping integrated historical replay for evaluation of %s/%s", model_name, model_version)
        else:
            try:
                from addressforge.services.replay_service import run_historical_replay

                logger.info("Triggering integrated historical replay for consistency check...")
                replay_result = run_historical_replay(
                    workspace_name=workspace_name,
                    candidate_version=model_version,
                    limit=5000,  # Large sample for stability check
                )
            except Exception as exc:  # noqa: BLE001
                replay_error = str(exc)
                logger.warning("Historical replay failed during evaluation for %s/%s: %s", model_name, model_version, exc)

        metrics_json["replay_metrics"] = {
            "processed_samples": int((replay_result or {}).get("processed") or 0),
            "consistency_score": _to_float((replay_result or {}).get("consistency_score")),
            "decision_match_rate": _to_float((replay_result or {}).get("decision_match_rate")),
            "building_type_match_rate": _to_float((replay_result or {}).get("building_type_match_rate")),
            "unit_number_match_rate": _to_float((replay_result or {}).get("unit_number_match_rate")),
            "disagreement_rate": _to_float((replay_result or {}).get("disagreement_rate")),
            "active_current_match_rate": _to_float((replay_result or {}).get("active_current_match_rate")),
            "candidate_current_match_rate": _to_float((replay_result or {}).get("candidate_current_match_rate")),
            "mismatches": int((replay_result or {}).get("mismatches") or 0),
            "failures": int((replay_result or {}).get("failures") or 0),
            "regression_detected": _to_float((replay_result or {}).get("disagreement_rate")),
            "status": "failed" if replay_error else "completed",
            "error": replay_error,
        }

        # 6. Generate Release Readiness Comparison
        # 6. 生成发布就绪对比
        active_model = get_active_model(workspace_name)
        active_release_benchmark: dict[str, Any] | None = None
        if active_model and not (
            active_model.get("model_name") == model_name and active_model.get("model_version") == model_version
        ):
            try:
                active_metrics = json.loads(active_model.get("metrics_json") or "{}")
                if isinstance(active_metrics, dict):
                    active_release_benchmark = active_metrics.get("release_benchmark")
            except Exception:
                active_release_benchmark = None
        
        # Merge Replay into Release Comparison
        # 将重放指标合并至发布对比中
        metrics_json["release_comparison"] = _compare_release_benchmark(
            metrics_json["release_benchmark"],
            active_release_benchmark,
        )
        metrics_json["release_comparison"]["regression_risk"] = metrics_json["replay_metrics"]["regression_detected"]
        metrics_json["release_comparison"]["replay_failures"] = metrics_json["replay_metrics"]["failures"]

        if decision_metrics and decision_metrics["total"] > 0:
            metric_name = "decision_f1"
            metric_value = float(decision_metrics["f1"])
        elif gold_count > 0:
            metric_name = "gold_coverage"
            metric_value = gold_coverage
        else:
            metric_name = "cleaning_coverage"
            metric_value = cleaning_coverage
        # Save Markdown Report
        artifact_dir = _artifact_dir()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        markdown_report = generate_markdown_report(metrics_json, locale=os.getenv("ADDRESSFORGE_LOCALE", "en"))
        # Add runtime identity to metrics for transparency
        # 将运行时标识添加到指标中以提高透明度
        total_eval = len(predicted)
        impact_rows = [r for r in predicted if r.get("reranker_impact_detected")]
        
        impact_by_direction: dict[str, int] = {}
        for r in impact_rows:
            detail = r.get("reranker_impact_detail") or {}
            key = f"{detail.get('heuristic_best_parser')} -> {detail.get('ml_best_parser')}"
            impact_by_direction[key] = impact_by_direction.get(key, 0) + 1

        metrics_json["reranker_metrics"] = {
            "impact_count": len(impact_rows),
            "impact_rate": round(len(impact_rows) / total_eval, 4) if total_eval > 0 else 0.0,
            "impact_by_direction": impact_by_direction,
            "impact_samples": [
                {
                    "raw_id": r.get("raw_id"),
                    "raw_text": r.get("raw_address_text"),
                    "h_parser": r.get("reranker_impact_detail", {}).get("heuristic_best_parser"),
                    "m_parser": r.get("reranker_impact_detail", {}).get("ml_best_parser"),
                }
                for r in impact_rows[:20]
            ]
        }
        
        metrics_json["runtime_identity"] = {
            "decision_model": target_runtime["model_service"].describe_runtime(),
            "reranker_model": target_runtime["reranker_service"].describe_runtime(),
            "parsers": list(target_runtime["parsers"]),
            "profile": target_runtime["profile"]
        }

        report_path = artifact_dir / f"{model_name}_{model_version}_eval.md"
        report_path.write_text(markdown_report, encoding="utf-8")
        
        artifact = EvaluationArtifact(
            run_id=run_id,
            workspace_name=workspace_name,
            model_name=model_name,
            model_version=model_version,
            dataset_name=dataset_name,
            sample_count=sample_count,
            cleaned_count=cleaned_count,
            cleaning_coverage=cleaning_coverage,
            gold_count=gold_count,
            gold_coverage=gold_coverage,
            metric_name=metric_name,
            metric_value=metric_value,
            metrics_json=metrics_json,
            report_path=str(report_path),
        )
        artifact_dir = _artifact_dir()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{model_name}_{model_version}_eval.json"
        artifact_path.write_text(json.dumps(asdict(artifact), ensure_ascii=False, indent=2), encoding="utf-8")
        existing_model = get_model(workspace_name, model_name, model_version)
        existing_metrics = _metrics_json_dict(existing_model)
        registry_row = register_model_version(
            workspace_name=workspace_name,
            model_name=model_name,
            model_version=model_version,
            status="evaluated",
            dataset_name=dataset_name,
            training_run_id=None,
            evaluation_run_id=run_id,
            artifact_path=str(artifact_path),
            metrics_json={
                **existing_metrics,
                "metric_name": artifact.metric_name,
                "metric_value": metric_value,
                **metrics_json,
            },
            notes=f"Evaluation completed for model={model_name}/{model_version} on dataset={dataset_name}. {metric_name}={metric_value:.4f}",
            is_default=0,
        )
        # 7. Final Artifact Creation & Markdown Reporting
        # 7. 最终产物创建与 Markdown 报告生成
        report_md = _generate_markdown_report(metrics_json, artifact)
        report_path = Path("runtime/reports") / f"{model_version}_release_report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_md, encoding="utf-8")

        finish_run(
            run_id,
            "completed",
            notes=f"Evaluation completed. metric={metric_name}:{metric_value:.4f}",
        )
        logger.info("Evaluation and Markdown report completed. Run ID: %s", run_id)
        return asdict(artifact)
    except Exception as exc:
        finish_run(run_id, "failed", notes=dumps_payload({"error": str(exc)}))
        raise

def _generate_markdown_report(metrics: dict[str, Any], artifact: EvaluationArtifact) -> str:
    """
    Generates a production-grade release report in Markdown format.
    生成生产级的 Markdown 格式发布报告。
    """
    report = [
        f"# AddressForge Release Report: {artifact.model_version}",
        f"**Workspace:** {artifact.workspace_name}",
        f"**Run ID:** {artifact.run_id}",
        "",
        "## 1. Core Accuracy (Gold Set)",
        "| Metric | Value | Status |",
        "| :--- | :--- | :--- |"
    ]
    
    benchmark = metrics.get("release_benchmark", {})
    report.append(f"| Decision F1 | {benchmark.get('decision_f1', 0.0):.4f} | {'PASS' if benchmark.get('decision_f1', 0.0) >= 0.90 else 'FAIL'} |")
    report.append(f"| Building Type F1 | {benchmark.get('building_type_f1', 0.0):.4f} | {'PASS' if benchmark.get('building_type_f1', 0.0) >= 0.85 else 'FAIL'} |")
    report.append(f"| Unit Recall | {benchmark.get('unit_recall', 0.0):.4f} | {'PASS' if benchmark.get('unit_recall', 0.0) >= 0.85 else 'FAIL'} |")

    shadow_assist = metrics.get("decision_shadow_assist") or {}
    if shadow_assist:
        heuristic = shadow_assist.get("heuristic") or {}
        ml_shadow = shadow_assist.get("ml_shadow") or {}
        assist_trial = shadow_assist.get("assist_trial") or {}
        report.extend([
            "",
            "## 1.1 DecisionModel Shadow-Assist",
            "| Metric | Heuristic | ML Shadow | Assist Trial |",
            "| :--- | :--- | :--- | :--- |",
            f"| Decision F1 | {float(heuristic.get('f1') or 0.0):.4f} | {float(ml_shadow.get('f1') or 0.0):.4f} | {float(assist_trial.get('f1') or 0.0):.4f} |",
            f"| Decision Precision | {float(heuristic.get('precision') or 0.0):.4f} | {float(ml_shadow.get('precision') or 0.0):.4f} | {float(assist_trial.get('precision') or 0.0):.4f} |",
            f"| Decision Recall | {float(heuristic.get('recall') or 0.0):.4f} | {float(ml_shadow.get('recall') or 0.0):.4f} | {float(assist_trial.get('recall') or 0.0):.4f} |",
            f"| Shadow Advantage | - | {float(shadow_assist.get('shadow_advantage') or 0.0):+.4f} |",
            f"| Assist Trial Advantage | - | - | {float(shadow_assist.get('assist_trial_advantage') or 0.0):+.4f} |",
            f"| Disagreement Rate | - | {float(shadow_assist.get('disagreement_rate') or 0.0):.4f} |",
        ])
        
    bt_shadow_assist = metrics.get("building_type_shadow_assist") or {}
    if bt_shadow_assist:
        bt_heuristic = bt_shadow_assist.get("heuristic") or {}
        bt_ml_shadow = bt_shadow_assist.get("ml_shadow") or {}
        bt_assist_summary = bt_shadow_assist.get("assist_summary") or {}
        report.extend([
            "",
            "## 1.2 BuildingTypeModel Shadow",
            "| Metric | Heuristic | ML Shadow |",
            "| :--- | :--- | :--- |",
            f"| Building Type F1 | {float(bt_heuristic.get('f1') or 0.0):.4f} | {float(bt_ml_shadow.get('f1') or 0.0):.4f} |",
            f"| Building Type Precision | {float(bt_heuristic.get('precision') or 0.0):.4f} | {float(bt_ml_shadow.get('precision') or 0.0):.4f} |",
            f"| Building Type Recall | {float(bt_heuristic.get('recall') or 0.0):.4f} | {float(bt_ml_shadow.get('recall') or 0.0):.4f} |",
            f"| Shadow Advantage | - | {float(bt_shadow_assist.get('shadow_advantage') or 0.0):+.4f} |",
        ])
        if bt_assist_summary:
            report.extend([
                "",
                "### BuildingType Assist Summary",
                "| Metric | Value |",
                "| :--- | :--- |",
                f"| Eligible Count | {int(bt_assist_summary.get('eligible_count') or 0)} |",
                f"| Applied Count | {int(bt_assist_summary.get('applied_count') or 0)} |",
                f"| Gold Match Rate | {float(bt_assist_summary.get('gold_match_rate') or 0.0):.4f} |",
                f"| Transition Counts | `{json.dumps(bt_assist_summary.get('transition_counts') or {}, ensure_ascii=False)}` |",
                f"| Applied Transition Counts | `{json.dumps(bt_assist_summary.get('applied_transition_counts') or {}, ensure_ascii=False)}` |",
            ])

    assist_readiness = metrics.get("decision_assist_rollout_readiness") or {}
    if assist_readiness:
        report.extend([
            "",
            "## 1.3 DecisionModel Assist Readiness",
            "| Check | Value | Status |",
            "| :--- | :--- | :--- |",
            f"| Rollout Status | {assist_readiness.get('status') or 'unknown'} | {'PASS' if assist_readiness.get('status') == 'ready_for_assist_trial' else 'HOLD'} |",
            f"| Shadow Advantage | {float(assist_readiness.get('shadow_advantage') or 0.0):+.4f} | {'PASS' if (assist_readiness.get('checks') or {}).get('shadow_beats_heuristic') else 'FAIL'} |",
            f"| Assist Trial Advantage | {float(assist_readiness.get('assist_trial_advantage') or 0.0):+.4f} | {'PASS' if (assist_readiness.get('checks') or {}).get('assist_trial_not_worse_than_shadow') else 'FAIL'} |",
            f"| Disagreement Rate | {float(assist_readiness.get('disagreement_rate') or 0.0):.4f} | {'PASS' if (assist_readiness.get('checks') or {}).get('disagreement_rate_safe') else 'FAIL'} |",
            f"| Eligible Assist Samples | {int(assist_readiness.get('eligible_count') or 0)} | {'PASS' if (assist_readiness.get('checks') or {}).get('eligible_sample_count_sufficient') else 'FAIL'} |",
            f"| Assist Gold Match Rate | {float(assist_readiness.get('assist_gold_match_rate') or 0.0):.4f} | {'PASS' if (assist_readiness.get('checks') or {}).get('assist_gold_match_rate_sufficient') else 'FAIL'} |",
        ])
    tuning_hints = metrics.get("decision_threshold_tuning_hints") or {}
    if tuning_hints:
        report.extend([
            "",
            "## 1.3 Decision Threshold Tuning Hints",
            f"- Overall Status: `{tuning_hints.get('status') or 'unknown'}`",
            f"- Next Action: {tuning_hints.get('next_action') or 'n/a'}",
        ])
        for hint in tuning_hints.get("hints") or []:
            thresholds = ", ".join(hint.get("candidate_thresholds") or [])
            threshold_text = f" Candidate thresholds: `{thresholds}`." if thresholds else ""
            report.append(
                f"- [{hint.get('priority')}] `{hint.get('target_bucket')}` -> {hint.get('suggestion')}{threshold_text}"
            )
    calibration = metrics.get("decision_policy_calibration_proposal") or {}
    if calibration:
        report.extend([
            "",
            "## 1.4 Decision Policy Calibration Proposal",
            f"- Status: `{calibration.get('status') or 'unknown'}`",
            f"- Apply Now: `{bool(calibration.get('apply_now'))}`",
            f"- Reason: {calibration.get('reason') or 'n/a'}",
        ])
        for item in calibration.get("recommended_changes") or []:
            report.append(
                f"- `{item.get('threshold')}` -> {item.get('direction')} by {item.get('step')}: {item.get('reason')}"
            )

    # --- Historical Replay & Stability Section ---
    report.extend([
        "",
        "## 2. Stability Analysis (Historical Replay)",
        "Analysis run over historical samples to detect regressions.",
        "",
        "| Indicator | Metric | Value |",
        "| :--- | :--- | :--- |"
    ])
    
    replay = metrics.get("replay_metrics", {})
    report.append(f"| Consistency | Consistency Score | {replay.get('consistency_score', 0.0):.4f} |")
    report.append(f"| Risk | Regression Detected | {replay.get('regression_detected', 0.0):.4f} |")

    # --- Release Comparison Section ---
    report.extend([
        "",
        "## 3. Candidate vs Active Comparison",
        "| Metric | Delta | Recommendation |",
        "| :--- | :--- | :--- |"
    ])
    
    comp = metrics.get("release_comparison", {})
    report.append(f"| Accuracy Shift | {comp.get('f1_delta', 0.0):+.4f} | {'IMPROVED' if comp.get('f1_delta', 0.0) > 0 else 'STABLE'} |")
    report.append(f"| Regression Risk | {comp.get('regression_risk', 0.0):.4f} | {'SAFE' if comp.get('regression_risk', 0.0) < 0.02 else 'HIGH RISK'} |")

    return "\n".join(report)
