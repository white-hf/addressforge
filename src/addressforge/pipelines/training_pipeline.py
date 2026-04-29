from __future__ import annotations

import json
from typing import Any

from addressforge.core.common import create_run, dumps_payload, finish_run, fetch_all
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.core.utils import logger
from addressforge.learning.trainer import run_baseline_training

def run_training_pipeline(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    model_name: str = "canada_default",
    model_version: str | None = None,
    gold_snapshot_id: int | None = None,
) -> dict[str, Any]:
    """
    Orchestrates the end-to-end model training process.
    编排端到端的模型训练全流程。
    """
    # 1. Generate version if not provided
    # 1. 如果未提供版本号，则自动生成
    if not model_version:
        import datetime
        model_version = f"v_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

    run_id = create_run("ml_train", notes=f"Pipeline start for {model_name}:{model_version}")
    logger.info("Pipeline started: %s version=%s", model_name, model_version)

    try:
        # 2. Identify Training Set from Gold Snapshots
        # 2. 从金标快照中确定训练集
        if gold_snapshot_id:
            snapshot_rows = fetch_all(
                "SELECT * FROM gold_set_snapshot WHERE snapshot_id = %s", (gold_snapshot_id,)
            )
        else:
            snapshot_rows = fetch_all(
                "SELECT * FROM gold_set_snapshot WHERE workspace_name = %s ORDER BY created_at DESC LIMIT 1",
                (workspace_name,)
            )

        if not snapshot_rows:
            logger.warning("No gold snapshot found. Training will use synthetic or existing base data.")
            dataset_source = "base_synthetic"
        else:
            dataset_source = f"snapshot_{snapshot_rows[0]['snapshot_id']}"
        
        # 3. Execution: Data Preparation & Training
        # 3. 执行：数据准备与训练
        # In a production scenario, we would export CSV/Parquet files here.
        # 在生产场景中，我们会在此处导出 CSV 或 Parquet 文件。
        training_result = run_baseline_training(
            workspace_name=workspace_name,
            dataset_name=dataset_source,
            model_name=model_name,
            model_version=model_version
        )

        finish_run(
            run_id,
            "completed",
            notes=dumps_payload(
                {
                    "pipeline": "automated_v1",
                    "source": dataset_source,
                    "trainer_run_id": training_result.get("run_id"),
                    "registry_model_id": training_result.get("registry_model_id"),
                    "artifact_path": training_result.get("artifact_path"),
                }
            ),
        )
        logger.info("Pipeline completed successfully. Model registered: %s", model_version)

        return {
            "status": "success",
            "model_id": training_result.get("registry_model_id"),
            "model_version": model_version,
            "run_id": run_id,
            "trainer_run_id": training_result.get("run_id"),
            "artifact_path": training_result.get("artifact_path"),
        }

    except Exception as exc:
        logger.exception("Training pipeline failed: %s", exc)
        finish_run(run_id, "failed", notes=str(exc))
        raise
