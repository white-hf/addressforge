from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from addressforge.core.common import create_run, dumps_payload, fetch_all, finish_run
from addressforge.core.config import (
    ADDRESSFORGE_MODEL_ARTIFACT_DIR,
    ADDRESSFORGE_MODEL_FAMILY,
    ADDRESSFORGE_MODEL_NAME,
    ADDRESSFORGE_MODEL_VERSION,
    ADDRESSFORGE_PROMOTE_AFTER_TRAIN,
    ADDRESSFORGE_WORKSPACE_NAME,
)
from addressforge.models import ensure_default_workspace, get_active_model, promote_model, register_model_version
from addressforge.core.utils import logger


@dataclass(frozen=True)
class TrainingArtifact:
    run_id: int
    workspace_name: str
    model_name: str
    model_version: str
    dataset_name: str
    sample_count: int
    eval_count: int
    metric_name: str
    metric_value: float


def _artifact_dir() -> Path:
    return Path(os.getenv("ADDRESSFORGE_MODEL_ARTIFACT_DIR", ADDRESSFORGE_MODEL_ARTIFACT_DIR)).expanduser()


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def run_baseline_training(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    model_name: str = ADDRESSFORGE_MODEL_NAME,
    model_version: str = ADDRESSFORGE_MODEL_VERSION,
    dataset_name: str = "default_training_set",
) -> dict[str, Any]:
    run_id = create_run("ml_export", notes=f"train model={model_name} dataset={dataset_name}")
    try:
        workspace = ensure_default_workspace()
        resolved_workspace = workspace.get("workspace_name") or workspace_name
        samples = fetch_all("SELECT COUNT(*) AS cnt FROM raw_address_record")
        labels = fetch_all("SELECT COUNT(*) AS cnt FROM external_building_reference WHERE is_active = 1")
        sample_count = int(samples[0]["cnt"]) if samples else 0
        eval_count = int(labels[0]["cnt"]) if labels else 0
        metric_value = 0.0
        if sample_count > 0:
            metric_value = min(0.99, round(eval_count / sample_count, 4))
        artifact = TrainingArtifact(
            run_id=run_id,
            workspace_name=resolved_workspace,
            model_name=model_name,
            model_version=model_version,
            dataset_name=dataset_name,
            sample_count=sample_count,
            eval_count=eval_count,
            metric_name="reference_coverage",
            metric_value=metric_value,
        )
        artifact_dir = _artifact_dir()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{model_name}_{model_version}.json"
        artifact_path.write_text(json.dumps(asdict(artifact), ensure_ascii=False, indent=2), encoding="utf-8")
        registry_row = register_model_version(
            workspace_name=resolved_workspace,
            model_name=model_name,
            model_version=model_version,
            model_family=os.getenv("ADDRESSFORGE_MODEL_FAMILY", ADDRESSFORGE_MODEL_FAMILY),
            status="trained",
            default_profile=os.getenv("ADDRESSFORGE_DEFAULT_PROFILE"),
            dataset_name=dataset_name,
            training_run_id=run_id,
            evaluation_run_id=run_id,
            reference_version=os.getenv("ADDRESSFORGE_REFERENCE_VERSION"),
            rule_version="baseline",
            artifact_path=str(artifact_path),
            metrics_json={
                "metric_name": artifact.metric_name,
                "metric_value": metric_value,
                "sample_count": sample_count,
                "eval_count": eval_count,
            },
            notes=dumps_payload(
                {
                    "artifact_path": str(artifact_path),
                    "model_name": model_name,
                    "model_version": model_version,
                    "dataset_name": dataset_name,
                    "sample_count": sample_count,
                    "eval_count": eval_count,
                    "metric_name": artifact.metric_name,
                    "metric_value": metric_value,
                }
            ),
            is_default=0,
        )
        active_model = get_active_model(resolved_workspace)
        if _truthy(os.getenv("ADDRESSFORGE_PROMOTE_AFTER_TRAIN", ADDRESSFORGE_PROMOTE_AFTER_TRAIN)) or not active_model:
            registry_row = promote_model(
                workspace_name=resolved_workspace,
                model_id=registry_row.get("model_id"),
                notes="auto-promoted after training",
            )
        finish_run(
            run_id,
            "completed",
            notes=dumps_payload(
                {
                    "workspace_name": resolved_workspace,
                    "artifact_path": str(artifact_path),
                    "model_name": model_name,
                    "model_version": model_version,
                    "dataset_name": dataset_name,
                    "sample_count": sample_count,
                    "eval_count": eval_count,
                    "metric_name": artifact.metric_name,
                    "metric_value": metric_value,
                    "registry_model_id": registry_row.get("model_id"),
                }
            ),
        )
        logger.info(
            "Training completed: run_id=%s workspace=%s model=%s version=%s dataset=%s samples=%s eval=%s metric=%s",
            run_id,
            resolved_workspace,
            model_name,
            model_version,
            dataset_name,
            sample_count,
            eval_count,
            metric_value,
        )
        return asdict(artifact)
    except Exception as exc:
        finish_run(run_id, "failed", notes=dumps_payload({"error": str(exc)}))
        raise


def main() -> None:
    workspace_name = os.getenv("ADDRESSFORGE_WORKSPACE_NAME", ADDRESSFORGE_WORKSPACE_NAME)
    model_name = os.getenv("ADDRESSFORGE_MODEL_NAME", ADDRESSFORGE_MODEL_NAME)
    model_version = os.getenv("ADDRESSFORGE_MODEL_VERSION", ADDRESSFORGE_MODEL_VERSION)
    dataset_name = os.getenv("ADDRESSFORGE_TRAINING_DATASET", "default_training_set")
    result = run_baseline_training(
        workspace_name=workspace_name,
        model_name=model_name,
        model_version=model_version,
        dataset_name=dataset_name,
    )
    print(result)


if __name__ == "__main__":
    main()
