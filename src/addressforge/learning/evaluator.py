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


def _extract_gold_value(label_json: dict[str, Any], field_name: str) -> str | None:
    if field_name == "decision":
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
    elif field_name == "building_type":
        value = row.get("building_type")
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
        (workspace_name,),
    )


def _resolve_model_runtime(
    workspace_name: str,
    model_name: str,
    model_version: str,
) -> tuple[str, tuple[str, ...], dict[str, Any] | None]:
    workspace = get_workspace(workspace_name) or {}
    target_model = get_model(workspace_name, model_name, model_version) or {}
    target_profile = (
        target_model.get("default_profile")
        or workspace.get("default_profile")
        or "base_canada"
    )
    target_parsers: tuple[str, ...] = ("simple_rule", "hybrid_canada", "libpostal")
    target_decision_policy: dict[str, Any] | None = None
    target_artifact_path = target_model.get("artifact_path")
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
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load target model artifact for runtime binding: %s", exc)
    return target_profile, target_parsers, target_decision_policy


def _predict_gold_rows_with_runtime(
    workspace_name: str,
    model_name: str,
    model_version: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not rows:
        return rows
    from addressforge.api.server import AddressPlatformService, AddressRequest

    target_profile, target_parsers, target_decision_policy = _resolve_model_runtime(
        workspace_name,
        model_name,
        model_version,
    )
    service = AddressPlatformService(
        default_profile=target_profile,
        default_parsers=target_parsers,
        decision_policy=target_decision_policy,
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
                        profile=target_profile,
                        parsers=list(target_parsers),
                        reranker_version=model_version,
                    )
                )
                current["decision"] = result.get("decision")
                current["building_type"] = result.get("building_type")
                current["suggested_unit_number"] = result.get("suggested_unit_number")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Runtime gold prediction failed for source_id=%s: %s", row.get("source_id"), exc)
                current["decision"] = None
                current["building_type"] = None
                current["suggested_unit_number"] = None
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
        if building_metrics:
            metrics_json["building_type"] = building_metrics
            errors = _field_error_samples(gold_rows, "building_type")
            metrics_json["building_type_errors"] = errors
            metrics_json["building_type_error_buckets"] = _generate_bucket_summary(errors)
        if unit_metrics:
            metrics_json["unit_number"] = unit_metrics
            errors = _field_error_samples(gold_rows, "unit_number")
            metrics_json["unit_number_errors"] = errors
            metrics_json["unit_number_error_buckets"] = _generate_bucket_summary(errors)
        if commercial_metrics:
            metrics_json["commercial"] = commercial_metrics
        benchmark_path = _default_canada_benchmark_path()
        if benchmark_path.exists():
            try:
                from addressforge.learning.canada_benchmark import run_canada_address_benchmark
                target_profile, target_parsers, target_decision_policy = _resolve_model_runtime(
                    workspace_name,
                    model_name,
                    model_version,
                )
                metrics_json["canada_benchmark"] = run_canada_address_benchmark(
                    benchmark_path,
                    workspace_name=workspace_name,
                    model_name=model_name,
                    model_version=model_version,
                    profile=target_profile,
                    parsers=target_parsers,
                    decision_policy=target_decision_policy,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Canada benchmark evaluation failed: %s", exc)
        # 5. Integration: Historical Replay & Consistency Check
        # 5. 集成：历史重放与一致性检查
        from addressforge.services.replay_service import run_historical_replay
        logger.info("Triggering integrated historical replay for consistency check...")
        replay_result = run_historical_replay(
            workspace_name=workspace_name,
            candidate_version=model_version,
            limit=5000 # Large sample for stability check
        )
        
        metrics_json["replay_metrics"] = {
            "processed_samples": replay_result.get("processed"),
            "consistency_score": _to_float(replay_result.get("consistency_score")),
            "decision_match_rate": _to_float(replay_result.get("decision_match_rate")),
            "building_type_match_rate": _to_float(replay_result.get("building_type_match_rate")),
            "unit_number_match_rate": _to_float(replay_result.get("unit_number_match_rate")),
            "disagreement_rate": _to_float(replay_result.get("disagreement_rate")),
            "active_current_match_rate": _to_float(replay_result.get("active_current_match_rate")),
            "candidate_current_match_rate": _to_float(replay_result.get("candidate_current_match_rate")),
            "mismatches": int(replay_result.get("mismatches") or 0),
            "failures": int(replay_result.get("failures") or 0),
            "regression_detected": _to_float(replay_result.get("disagreement_rate")),
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
                "metric_name": artifact.metric_name,
                "metric_value": metric_value,
                **metrics_json,
            },
            notes=dumps_payload(
                {
                    "artifact_path": str(artifact_path),
                    "model_name": model_name,
                    "model_version": model_version,
                    "dataset_name": dataset_name,
                    **metrics_json,
                }
            ),
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
            notes=dumps_payload(
                {
                    "workspace_name": workspace_name,
                    "artifact_path": str(artifact_path),
                    "report_path": str(report_path),
                    "model_name": model_name,
                    "model_version": model_version,
                    **metrics_json,
                }
            ),
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
    report.append(f"| Unit Recall | {benchmark.get('unit_recall', 0.0):.4f} | {'PASS' if benchmark.get('unit_recall', 0.0) >= 0.85 else 'FAIL'} |")

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
