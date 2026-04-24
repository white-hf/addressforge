from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from addressforge.core.common import create_run, dumps_payload, fetch_all, finish_run
from addressforge.core.utils import logger


@dataclass(frozen=True)
class TrainingArtifact:
    run_id: int
    model_name: str
    dataset_name: str
    sample_count: int
    eval_count: int
    metric_name: str
    metric_value: float


def _artifact_dir() -> Path:
    return Path(os.getenv("ADDRESSFORGE_MODEL_DIR", "models/default_canada")).expanduser()


def run_baseline_training(
    model_name: str = "canada_default_v1",
    dataset_name: str = "default_training_set",
) -> dict[str, Any]:
    run_id = create_run("ml_export", notes=f"train model={model_name} dataset={dataset_name}")
    try:
        samples = fetch_all("SELECT COUNT(*) AS cnt FROM raw_address_record")
        labels = fetch_all("SELECT COUNT(*) AS cnt FROM external_building_reference WHERE is_active = 1")
        sample_count = int(samples[0]["cnt"]) if samples else 0
        eval_count = int(labels[0]["cnt"]) if labels else 0
        metric_value = 0.0
        if sample_count > 0:
            metric_value = min(0.99, round(eval_count / sample_count, 4))
        artifact = TrainingArtifact(
            run_id=run_id,
            model_name=model_name,
            dataset_name=dataset_name,
            sample_count=sample_count,
            eval_count=eval_count,
            metric_name="reference_coverage",
            metric_value=metric_value,
        )
        artifact_dir = _artifact_dir()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{model_name}.json"
        artifact_path.write_text(json.dumps(asdict(artifact), ensure_ascii=False, indent=2), encoding="utf-8")
        finish_run(
            run_id,
            "completed",
            notes=dumps_payload(
                {
                    "artifact_path": str(artifact_path),
                    "model_name": model_name,
                    "dataset_name": dataset_name,
                    "sample_count": sample_count,
                    "eval_count": eval_count,
                    "metric_name": artifact.metric_name,
                    "metric_value": metric_value,
                }
            ),
        )
        logger.info(
            "Training completed: run_id=%s model=%s dataset=%s samples=%s eval=%s metric=%s",
            run_id,
            model_name,
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
    model_name = os.getenv("ADDRESSFORGE_MODEL_NAME", "canada_default_v1")
    dataset_name = os.getenv("ADDRESSFORGE_TRAINING_DATASET", "default_training_set")
    result = run_baseline_training(model_name=model_name, dataset_name=dataset_name)
    print(result)


if __name__ == "__main__":
    main()
