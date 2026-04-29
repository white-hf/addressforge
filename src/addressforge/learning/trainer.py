from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from addressforge.core.common import create_run, dumps_payload, fetch_all, finish_run
from addressforge.core.config import (
    ADDRESSFORGE_MODEL_ARTIFACT_DIR,
    ADDRESSFORGE_MODEL_FAMILY,
    ADDRESSFORGE_WORKSPACE_NAME,
)
from addressforge.learning.canada_benchmark import run_canada_address_benchmark
from addressforge.models import get_model, get_workspace, register_model_version


def _artifact_dir() -> Path:
    return Path(os.getenv("ADDRESSFORGE_MODEL_ARTIFACT_DIR", ADDRESSFORGE_MODEL_ARTIFACT_DIR)).expanduser()


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
        SELECT g.label_json, acr.validation_json
        FROM gold_label g
        JOIN address_cleaning_result acr
          ON acr.workspace_name = g.workspace_name
         AND CAST(acr.raw_id AS CHAR) = g.source_id
        WHERE g.workspace_name = %s
          AND g.review_status = 'accepted'
          AND g.label_source = 'human'
        ORDER BY g.gold_label_id ASC
        """,
        (workspace_name,),
    )
    commercial_accept_scores: list[float] = []
    multi_unit_accept_scores: list[float] = []
    accept_scores: list[float] = []
    review_scores: list[float] = []
    reject_scores: list[float] = []
    gps_reference_scores: list[float] = []

    for row in rows:
        try:
            label = json.loads(row.get("label_json") or "{}")
            validation = json.loads(row.get("validation_json") or "{}")
        except Exception:
            continue
        if not isinstance(label, dict) or not isinstance(validation, dict):
            continue
        gold_decision = str(label.get("decision") or "").strip().lower()
        gold_building = str(label.get("building_type") or "").strip().lower()
        score = _safe_float(validation.get("confidence"), 0.0)
        ref_score = _safe_float((validation.get("hints") or {}).get("reference_score"), 0.0)
        if gold_decision == "accept":
            accept_scores.append(score)
            if gold_building == "commercial":
                commercial_accept_scores.append(score)
            if gold_building == "multi_unit":
                multi_unit_accept_scores.append(score)
        elif gold_decision == "review":
            review_scores.append(score)
        elif gold_decision == "reject":
            reject_scores.append(score)
        if ref_score > 0:
            gps_reference_scores.append(ref_score)

    policy = dict(defaults)
    if commercial_accept_scores:
        policy["commercial_accept_threshold"] = round(max(0.7, min(commercial_accept_scores) - 0.01), 4)
    if multi_unit_accept_scores:
        policy["multi_unit_accept_threshold"] = round(max(0.55, min(multi_unit_accept_scores) - 0.01), 4)
    if accept_scores:
        policy["high_confidence_accept_threshold"] = round(max(0.65, min(accept_scores) - 0.01), 4)
    if review_scores:
        policy["moderate_confidence_review_threshold"] = round(max(0.4, min(review_scores) - 0.01), 4)
        policy["parser_disagreement_review_threshold"] = policy["moderate_confidence_review_threshold"]
        policy["commercial_review_threshold"] = policy["moderate_confidence_review_threshold"]
    if reject_scores:
        candidate = round(max(reject_scores) + 0.01, 4)
        policy["moderate_confidence_review_threshold"] = max(policy["moderate_confidence_review_threshold"], candidate)
    if gps_reference_scores:
        policy["gps_weak_match_threshold"] = round(max(0.5, min(gps_reference_scores)), 4)
        policy["gps_conflict_threshold"] = round(max(0.4, min(gps_reference_scores) - 0.05), 4)
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
            SELECT COUNT(*) AS cnt
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
        parser_weights = _derive_parser_weights(
            workspace_name,
            model_name=model_name,
            model_version=model_version,
            profile=profile,
            decision_policy=decision_policy,
        )
        decision_policy["parser_weights"] = parser_weights

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
                "canada_benchmark": benchmark_summary,
            },
            notes=dumps_payload(artifact_payload),
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
