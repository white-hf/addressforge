from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from addressforge.core.common import (
    create_run,
    db_cursor,
    dumps_payload,
    ensure_etl_run_types,
    fetch_all,
    finish_run,
    transaction_cursor,
)
from addressforge.core.config import (
    ADDRESSFORGE_INGESTION_API_BATCH_SIZE,
    ADDRESSFORGE_INGESTION_DB_BATCH_SIZE,
    ADDRESSFORGE_INGESTION_DB_CITY_COLUMN,
    ADDRESSFORGE_INGESTION_DB_CURSOR_COLUMN,
    ADDRESSFORGE_INGESTION_DB_EXTERNAL_ID_COLUMN,
    ADDRESSFORGE_INGESTION_DB_HOST,
    ADDRESSFORGE_INGESTION_DB_LATITUDE_COLUMN,
    ADDRESSFORGE_INGESTION_DB_LONGITUDE_COLUMN,
    ADDRESSFORGE_INGESTION_DB_NAME,
    ADDRESSFORGE_INGESTION_DB_PASSWORD,
    ADDRESSFORGE_INGESTION_DB_POSTAL_CODE_COLUMN,
    ADDRESSFORGE_INGESTION_DB_PROVINCE_COLUMN,
    ADDRESSFORGE_INGESTION_DB_RAW_ADDRESS_COLUMN,
    ADDRESSFORGE_INGESTION_DB_TABLE,
    ADDRESSFORGE_INGESTION_DB_TIEBREAKER_COLUMN,
    ADDRESSFORGE_INGESTION_DB_USER,
    ADDRESSFORGE_INGESTION_MODE,
    ADDRESSFORGE_INGESTION_SOURCE_NAME,
    ADDRESSFORGE_MODEL_NAME,
    ADDRESSFORGE_MODEL_VERSION,
    ADDRESSFORGE_WORKSPACE_NAME,
)
from addressforge.core.utils import logger, ttl_cache
from addressforge.ingestion.service import IngestionService
from addressforge.ingestion.providers import ApiIngestionProvider, DatabaseIngestionProvider, resolve_ingestion_provider
from addressforge.core.reference import ExternalReferenceImportService
from addressforge.learning.evaluator import run_baseline_evaluation
from addressforge.learning.gold import freeze_gold_set, seed_active_learning_queue
from addressforge.learning.shadow import run_baseline_shadow
from addressforge.learning.trainer import run_baseline_training
from addressforge.pipelines.export_snapshot import export_workspace_snapshot
from addressforge.models import bootstrap_default_registry, promote_model


CONTROL_JOB_KINDS = (
    "ingestion_once",
    "reference_import_once",
    "workspace_export_once",
    "cleaning_once",
    "training_once",
    "evaluation_once",
    "shadow_once",
    "gold_freeze_once",
    "active_learning_once",
    "promote_assets_once",
    "evolution_once",
    "reload_models_once",
    "bootstrap_registry",
)
CONTROL_JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
WORKER_HEARTBEAT_TIMEOUT_SECONDS = 30
# Increased to 15 minutes for slow ML tasks
# 增加到 15 分钟，以适应缓慢的 ML 任务
STALE_RUNNING_JOB_TIMEOUT_SECONDS = 900


@dataclass(frozen=True)
class ControlJobRecord:
    job_id: int
    workspace_name: str
    job_kind: str
    status: str
    priority: int
    requested_by: str | None
    claimed_by: str | None
    payload_json: str | None
    result_json: str | None
    error_text: str | None
    etl_run_id: int | None
    created_at: str | None
    claimed_at: str | None
    started_at: str | None
    finished_at: str | None
    updated_at: str | None


def _json_or_none(value: dict[str, Any] | list[Any] | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return dumps_payload(value if isinstance(value, dict) else {"value": value})


def _truthy_setting(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


_CONTROL_CENTER_BOOTSTRAPPED = False

def bootstrap_control_center() -> dict[str, Any]:
    global _CONTROL_CENTER_BOOTSTRAPPED
    registry = bootstrap_default_registry()
    
    if _CONTROL_CENTER_BOOTSTRAPPED:
        return registry
        
    workspace_name = registry["workspace"]["workspace_name"]
    default_settings = {
        "continuous_mode.enabled": False,
        "continuous_mode.interval_seconds": 300,
        "continuous_mode.last_trigger_at": "",
        "ingestion.retry.max_attempts": 3,
        "ingestion.alert_status": "ok",
        "ingestion.last_error": "",
        "ingestion.last_failed_cursor": "",
        "ingestion.retry_job_id": "",
        "ingestion.consecutive_failures": 0,
        "ingestion.mode": ADDRESSFORGE_INGESTION_MODE,
        "ingestion.source_name": ADDRESSFORGE_INGESTION_SOURCE_NAME,
        "ingestion.api.batch_size": ADDRESSFORGE_INGESTION_API_BATCH_SIZE,
        "ingestion.db.batch_size": ADDRESSFORGE_INGESTION_DB_BATCH_SIZE,
        "ingestion.db.table": ADDRESSFORGE_INGESTION_DB_TABLE,
        "ingestion.db.cursor_column": ADDRESSFORGE_INGESTION_DB_CURSOR_COLUMN,
        "ingestion.db.tiebreaker_column": ADDRESSFORGE_INGESTION_DB_TIEBREAKER_COLUMN,
        "ingestion.db.external_id_column": ADDRESSFORGE_INGESTION_DB_EXTERNAL_ID_COLUMN,
        "ingestion.db.raw_address_column": ADDRESSFORGE_INGESTION_DB_RAW_ADDRESS_COLUMN,
        "ingestion.db.city_column": ADDRESSFORGE_INGESTION_DB_CITY_COLUMN,
        "ingestion.db.province_column": ADDRESSFORGE_INGESTION_DB_PROVINCE_COLUMN,
        "ingestion.db.postal_code_column": ADDRESSFORGE_INGESTION_DB_POSTAL_CODE_COLUMN,
        "ingestion.db.latitude_column": ADDRESSFORGE_INGESTION_DB_LATITUDE_COLUMN,
        "ingestion.db.longitude_column": ADDRESSFORGE_INGESTION_DB_LONGITUDE_COLUMN,
        "pipeline.auto_clean.enabled": True,
        "pipeline.auto_train.enabled": False,
        "pipeline.auto_eval.enabled": True,
        "pipeline.auto_shadow.enabled": True,
        "pipeline.auto_active_learning.enabled": True,
        "pipeline.auto_promote.enabled": False,
        "pipeline.auto_promote.min_delta": 0.0,
    }
    for key, value in default_settings.items():
        existing = get_setting(workspace_name, key, None)
        if existing is None:
            set_setting(workspace_name, key, value)
            
    _CONTROL_CENTER_BOOTSTRAPPED = True
    return registry


def create_job(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    job_kind: str = "ingestion_once",
    payload: dict[str, Any] | None = None,
    requested_by: str | None = None,
    priority: int = 0,
) -> dict[str, Any]:
    if job_kind not in CONTROL_JOB_KINDS:
        raise ValueError(f"Unsupported job kind: {job_kind}")
    payload_json = _json_or_none(payload)
    with db_cursor() as (conn, cursor):
        cursor.execute(
            """
            INSERT INTO control_job (
                workspace_name, job_kind, status, priority, requested_by, payload_json
            ) VALUES (%s, %s, 'queued', %s, %s, %s)
            """,
            (workspace_name, job_kind, priority, requested_by, payload_json),
        )
        conn.commit()
        return get_job(int(cursor.lastrowid)) or {}


def get_job(job_id: int) -> dict[str, Any] | None:
    rows = fetch_all("SELECT * FROM control_job WHERE job_id = %s LIMIT 1", (job_id,))
    return rows[0] if rows else None


def get_job_details(job_id: int) -> dict[str, Any] | None:
    job = get_job(job_id)
    if not job:
        return None
    if job.get("payload_json"):
        try:
            job["payload"] = json.loads(str(job["payload_json"]))
        except Exception:
            job["payload"] = job.get("payload_json")
    if job.get("result_json"):
        try:
            job["result"] = json.loads(str(job["result_json"]))
        except Exception:
            job["result"] = job.get("result_json")
    job["steps"] = _summarize_job_steps(job)
    job["result_summary"] = _summarize_job_result(job)
    return job


def _step(label: str, status: str, detail: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"label": label, "status": status}
    if detail:
        item["detail"] = detail
    return item


def _summarize_job_steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    followup = result.get("followup_job") if isinstance(result, dict) else None
    followups = result.get("followup_jobs") if isinstance(result, dict) else None
    promotion_result = result.get("promotion_result") if isinstance(result, dict) else None
    steps: list[dict[str, Any]] = []
    kind = str(job.get("job_kind") or "")
    if kind == "ingestion_once":
        steps.append(_step("Ingestion", "completed" if job.get("status") == "succeeded" else job.get("status", "queued")))
        if followup:
            steps.append(_step("Auto-clean follow-up", "queued", f"job_id={followup.get('job_id')}"))
    elif kind == "cleaning_once":
        steps.append(_step("Cleaning", "completed" if job.get("status") == "succeeded" else job.get("status", "queued")))
        if followup:
            detail = f"job_id={followup.get('job_id')}"
            if isinstance(result.get("result"), dict) and result["result"].get("has_more"):
                steps.append(_step("Auto-clean next page", "queued", detail))
            else:
                steps.append(_step("Auto-train follow-up", "queued", detail))
    elif kind == "training_once":
        steps.append(_step("Training", "completed" if job.get("status") == "succeeded" else job.get("status", "queued")))
        if followup:
            steps.append(_step("Auto-eval follow-up", "queued", f"job_id={followup.get('job_id')}"))
    elif kind == "evaluation_once":
        steps.append(_step("Evaluation", "completed" if job.get("status") == "succeeded" else job.get("status", "queued")))
        if followup:
            steps.append(_step("Auto-shadow follow-up", "queued", f"job_id={followup.get('job_id')}"))
    elif kind == "shadow_once":
        steps.append(_step("Shadow", "completed" if job.get("status") == "succeeded" else job.get("status", "queued")))
        if followup:
            steps.append(_step("Auto-active-learning follow-up", "queued", f"job_id={followup.get('job_id')}"))
        if promotion_result:
            steps.append(
                _step(
                    "Auto-promote",
                    "completed",
                    f"{promotion_result.get('model_name')} {promotion_result.get('model_version')}",
                )
            )
        if followups and isinstance(followups, list) and len(followups) > 1:
            steps.append(_step("Additional follow-ups", "queued", f"count={len(followups)}"))
    elif kind == "gold_freeze_once":
        steps.append(_step("Freeze gold", "completed" if job.get("status") == "succeeded" else job.get("status", "queued")))
    elif kind == "active_learning_once":
        steps.append(_step("Active learning seed", "completed" if job.get("status") == "succeeded" else job.get("status", "queued")))
    elif kind == "reference_import_once":
        steps.append(_step("Reference import", "completed" if job.get("status") == "succeeded" else job.get("status", "queued")))
    elif kind == "workspace_export_once":
        steps.append(_step("Workspace export", "completed" if job.get("status") == "succeeded" else job.get("status", "queued")))
    elif kind == "bootstrap_registry":
        steps.append(_step("Bootstrap registry", "completed" if job.get("status") == "succeeded" else job.get("status", "queued")))
    else:
        steps.append(_step(kind or "job", str(job.get("status") or "queued")))
    return steps


def _summarize_job_result(job: dict[str, Any]) -> str:
    result = job.get("result")
    if not isinstance(result, dict):
        return str(result or "—")
    kind = str(job.get("job_kind") or "")
    parts: list[str] = []
    if kind == "ingestion_once":
        # Robustly try to find ingested count from nested result or top level
        # 稳健地尝试从嵌套结果或顶层寻找摄取数量
        ingested = None
        if isinstance(result.get("result"), dict):
            ingested = result["result"].get("records_ingested")
        if ingested is None:
            ingested = result.get("records_ingested")
            
        parts.append(f"records_ingested={ingested if ingested is not None else 'n/a'}")
        if result.get("followup_job"):
            parts.append(f"followup_job_id={result['followup_job'].get('job_id')}")
    elif kind == "cleaning_once":
        cleaned = result.get("result", {}).get("records_processed") if isinstance(result.get("result"), dict) else None
        parts.append(f"records_processed={cleaned if cleaned is not None else 'n/a'}")
        if isinstance(result.get("result"), dict):
            checkpoint_stage = result["result"].get("checkpoint_stage")
            if checkpoint_stage:
                parts.append(f"stage={checkpoint_stage}")
        if result.get("followup_job"):
            parts.append(f"followup_job_id={result['followup_job'].get('job_id')}")
    elif kind == "training_once":
        parts.append(f"model={result.get('model_name')} {result.get('model_version')}")
        if isinstance(result.get("result"), dict):
            metrics = result["result"]
            parts.append(
                f"coverage={metrics.get('cleaning_coverage', metrics.get('eval_coverage', metrics.get('coverage', 'n/a')))}"
            )
        if result.get("followup_job"):
            parts.append(f"followup_job_id={result['followup_job'].get('job_id')}")
    elif kind == "evaluation_once":
        parts.append(f"model={result.get('model_name')} {result.get('model_version')}")
        if isinstance(result.get("result"), dict):
            metrics = result["result"]
            parts.append(f"score={metrics.get('f1', metrics.get('accuracy', 'n/a'))}")
        if result.get("followup_job"):
            parts.append(f"followup_job_id={result['followup_job'].get('job_id')}")
    elif kind == "shadow_once":
        shadow = result.get("result") if isinstance(result.get("result"), dict) else {}
        parts.append(f"candidate={shadow.get('candidate_model_name', result.get('model_name'))} {shadow.get('candidate_model_version', result.get('model_version'))}")
        parts.append(f"active={shadow.get('active_model_name', '—')} {shadow.get('active_model_version', '—')}")
        parts.append(f"delta={shadow.get('score_delta', 'n/a')}")
        parts.append(f"decision={shadow.get('decision', 'n/a')}")
        if result.get("followup_job"):
            parts.append(f"followup_job_id={result['followup_job'].get('job_id')}")
        followups = result.get("followup_jobs")
        if isinstance(followups, list) and followups:
            parts.append(f"followup_jobs={len(followups)}")
        promotion_result = result.get("promotion_result")
        if isinstance(promotion_result, dict) and promotion_result:
            parts.append(f"promoted={promotion_result.get('model_name')} {promotion_result.get('model_version')}")
    elif kind == "gold_freeze_once":
        if isinstance(result.get("result"), dict):
            stats = result["result"]
            parts.append(f"gold_set_version={stats.get('gold_set_version', 'n/a')}")
            parts.append(f"samples={stats.get('sample_count', 'n/a')}")
            parts.append(f"train={stats.get('train_count', 'n/a')}")
            parts.append(f"eval={stats.get('eval_count', 'n/a')}")
            parts.append(f"test={stats.get('test_count', 'n/a')}")
    elif kind == "active_learning_once":
        if isinstance(result.get("result"), dict):
            stats = result["result"]
            parts.append(f"inserted={stats.get('inserted', 'n/a')}")
            parts.append(f"threshold={stats.get('confidence_threshold', 'n/a')}")
    elif kind == "reference_import_once":
        if isinstance(result.get("result"), dict):
            stats = result["result"]
            parts.append(f"rows={stats.get('inserted', stats.get('records_ingested', 'n/a'))}")
    elif kind == "workspace_export_once":
        if isinstance(result.get("result"), dict):
            stats = result["result"]
            parts.append(f"rows={stats.get('total_rows', 'n/a')}")
            parts.append(f"dir={stats.get('export_dir', 'n/a')}")
    else:
        if isinstance(result, dict):
            parts.append(", ".join(f"{key}={value}" for key, value in list(result.items())[:4]) or "n/a")
    return " · ".join(parts) if parts else "—"


def _decoded_payload(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload")
    if isinstance(payload, dict):
        return payload
    raw = job.get("payload_json")
    if not raw:
        return {}
    try:
        data = json.loads(str(raw))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _decoded_result(job: dict[str, Any]) -> dict[str, Any]:
    result = job.get("result")
    if isinstance(result, dict):
        return result
    raw = job.get("result_json")
    if not raw:
        return {}
    try:
        data = json.loads(str(raw))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def summarize_latest_ingestion_cleaning_batch(workspace_name: str) -> dict[str, Any]:
    """
    Summarize the latest ingestion batch and its downstream cleaning jobs.
    汇总最新一次导入批次及其后续清洗任务。
    """
    reconcile_stale_running_jobs(workspace_name)
    ingestion_rows = fetch_all(
        """
        SELECT *
        FROM control_job
        WHERE workspace_name = %s
          AND job_kind = 'ingestion_once'
        ORDER BY created_at DESC, job_id DESC
        LIMIT 5
        """,
        (workspace_name,),
    )
    if not ingestion_rows:
        return {
            "workspace_name": workspace_name,
            "has_batch": False,
        }

    latest_ingestion = ingestion_rows[0]
    latest_ingestion_job_id = int(latest_ingestion["job_id"])
    latest_ingestion_created_at = latest_ingestion.get("created_at")
    cleaning_query = """
        SELECT *
        FROM control_job
        WHERE workspace_name = %s
          AND job_kind = 'cleaning_once'
          AND created_at >= %s
    """
    params: list[Any] = [workspace_name, latest_ingestion_created_at]
    cleaning_query += " ORDER BY created_at ASC, job_id ASC"
    cleaning_rows = fetch_all(cleaning_query, tuple(params))

    imported_count = 0
    ingestion_result = _decoded_result(latest_ingestion)
    if isinstance(ingestion_result.get("result"), dict):
        imported_count = int(ingestion_result["result"].get("records_ingested") or 0)

    cleaned_count = 0
    cleaning_succeeded = 0
    cleaning_failed = 0
    cleaning_running = 0
    cleaning_queued = 0
    latest_cleaning_finished_at = None
    related_cleaning_job_ids: list[int] = []
    for job in cleaning_rows:
        related_cleaning_job_ids.append(int(job["job_id"]))
        status = str(job.get("status") or "")
        if status == "succeeded":
            cleaning_succeeded += 1
            result = _decoded_result(job)
            if isinstance(result.get("result"), dict):
                cleaned_count += int(result["result"].get("records_processed") or 0)
            latest_cleaning_finished_at = job.get("finished_at") or latest_cleaning_finished_at
        elif status == "failed":
            cleaning_failed += 1
        elif status == "running":
            cleaning_running += 1
        elif status == "queued":
            cleaning_queued += 1

    latest_cleaning_job = cleaning_rows[-1] if cleaning_rows else None
    return {
        "workspace_name": workspace_name,
        "has_batch": True,
        "latest_ingestion_job_id": latest_ingestion_job_id,
        "latest_ingestion_status": latest_ingestion.get("status"),
        "latest_ingestion_created_at": latest_ingestion_created_at,
        "latest_ingestion_finished_at": latest_ingestion.get("finished_at"),
        "records_ingested": imported_count,
        "related_cleaning_job_ids": related_cleaning_job_ids,
        "cleaning_job_count": len(cleaning_rows),
        "records_cleaned": cleaned_count,
        "cleaning_succeeded": cleaning_succeeded,
        "cleaning_failed": cleaning_failed,
        "cleaning_running": cleaning_running,
        "cleaning_queued": cleaning_queued,
        "latest_cleaning_job_id": int(latest_cleaning_job["job_id"]) if latest_cleaning_job else None,
        "latest_cleaning_status": latest_cleaning_job.get("status") if latest_cleaning_job else None,
        "latest_cleaning_finished_at": latest_cleaning_finished_at,
    }


def list_jobs_full(
    workspace_name: str | None = None,
    status: str | None = None,
    job_kind: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM control_job WHERE 1=1"
    params: list[Any] = []
    if workspace_name:
        query += " AND workspace_name = %s"
        params.append(workspace_name)
    if status:
        query += " AND status = %s"
        params.append(status)
    if job_kind:
        query += " AND job_kind = %s"
        params.append(job_kind)
    query += " ORDER BY priority DESC, created_at DESC, job_id DESC LIMIT %s"
    params.append(limit)
    return fetch_all(query, tuple(params))


@ttl_cache(seconds=300)
def count_jobs(workspace_name: str | None = None) -> dict[str, int]:
    if workspace_name:
        reconcile_stale_running_jobs(workspace_name)
    query = """
        SELECT status, COUNT(*) AS cnt
        FROM control_job
        WHERE 1=1
    """
    params: list[Any] = []
    if workspace_name:
        query += " AND workspace_name = %s"
        params.append(workspace_name)
    query += " GROUP BY status"
    rows = fetch_all(query, tuple(params))
    counts = {status: 0 for status in CONTROL_JOB_STATUSES}
    for row in rows:
        counts[str(row["status"])] = int(row["cnt"])
    return counts

@ttl_cache(seconds=300)
def count_jobs_by_kind(workspace_name: str | None = None) -> dict[str, int]:
    if workspace_name:
        reconcile_stale_running_jobs(workspace_name)
    query = """
        SELECT job_kind, COUNT(*) AS cnt
        FROM control_job
        WHERE 1=1
    """
    params: list[Any] = []
    if workspace_name:
        query += " AND workspace_name = %s"
        params.append(workspace_name)
    query += " GROUP BY job_kind"
    rows = fetch_all(query, tuple(params))
    counts = {job_kind: 0 for job_kind in CONTROL_JOB_KINDS}
    for row in rows:
        counts[str(row["job_kind"])] = int(row["cnt"])
    return counts


@ttl_cache(seconds=300)
def count_cleaning_results(workspace_name: str, decision: str | None = None) -> int:
    """
    Counts records in the cleaning result table, optionally filtered by decision.
    统计清洗结果表中的记录数，可选按决策过滤。
    """
    query = "SELECT COUNT(*) as cnt FROM address_cleaning_result WHERE workspace_name = %s"
    params = [workspace_name]
    if decision:
        query += " AND decision = %s"
        params.append(decision)
    
    rows = fetch_all(query, tuple(params))
    return int(rows[0]["cnt"]) if rows else 0


@ttl_cache(seconds=600)
def count_available_for_review(workspace_name: str, confidence_threshold: float = 0.55) -> int:
    """
    Counts high-value samples that are suggested for review but haven't been queued or labeled yet.
    Optimized to perform filtering in memory to avoid slow SQL type-conversion joins.
    统计建议审核但尚未进入队列或标记的高价值样本。已优化为在内存中进行过滤，以避免慢速 SQL 类型转换连接。
    """
    # 1. Fetch potential candidates (small subset of the large table)
    # 1. 获取潜在候选对象（大表的一小部分子集）
    candidates = fetch_all(
        """
        SELECT raw_id 
        FROM address_cleaning_result 
        WHERE workspace_name = %s 
          AND (decision = 'review' OR confidence <= %s)
        """,
        (workspace_name, confidence_threshold)
    )
    if not candidates:
        return 0
        
    # 2. Fetch already queued/labeled IDs (usually a small number)
    # 2. 获取已进入队列/标记的 ID（通常数量较少）
    queued = fetch_all(
        "SELECT source_id FROM active_learning_queue WHERE workspace_name = %s",
        (workspace_name,)
    )
    labeled = fetch_all(
        "SELECT source_id FROM gold_label WHERE workspace_name = %s",
        (workspace_name,)
    )
    
    # 3. Perform high-speed set difference in memory
    # 3. 在内存中进行高速集合差集计算
    candidate_set = {str(r["raw_id"]) for r in candidates}
    queued_set = {str(r["source_id"]) for r in queued}
    labeled_set = {str(r["source_id"]) for r in labeled}
    
    available = candidate_set - queued_set - labeled_set
    return len(available)


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text[:19], text):
        try:
            return datetime.strptime(candidate, "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
    return None


def _worker_last_seen_map(workspace_name: str) -> dict[str, datetime]:
    rows = fetch_all(
        """
        SELECT setting_key, setting_value
        FROM control_setting
        WHERE workspace_name = %s
          AND setting_key LIKE 'worker.%.last_seen'
          AND setting_key <> 'worker.global.last_seen'
        """,
        (workspace_name,),
    )
    result: dict[str, datetime] = {}
    for row in rows:
        setting_key = str(row.get("setting_key") or "")
        worker_name = setting_key.removeprefix("worker.").removesuffix(".last_seen")
        last_seen = _parse_timestamp(row.get("setting_value"))
        if worker_name and last_seen:
            result[worker_name] = last_seen
    return result


def _active_worker_names(workspace_name: str, timeout_seconds: int = WORKER_HEARTBEAT_TIMEOUT_SECONDS) -> set[str]:
    now = datetime.now()
    return {
        worker_name
        for worker_name, last_seen in _worker_last_seen_map(workspace_name).items()
        if (now - last_seen).total_seconds() < timeout_seconds
    }


def reconcile_stale_running_jobs(
    workspace_name: str,
    *,
    stale_after_seconds: int = STALE_RUNNING_JOB_TIMEOUT_SECONDS,
) -> list[int]:
    """
    Identifies and fails jobs that are stuck in 'running' status.
    识别并使停留在“运行中 (running)”状态的任务失败。
    """
    # 1. Quick check for running jobs
    # 1. 快速检查运行中的任务
    running_jobs = fetch_all(
        """
        SELECT job_id, claimed_by, started_at, updated_at
        FROM control_job
        WHERE workspace_name = %s AND status = 'running'
        """,
        (workspace_name,),
    )
    if not running_jobs:
        return []

    # 2. Only check activity for workers who have running jobs
    # 2. 仅检查有运行中任务的 worker 的活动
    worker_names = {str(j["claimed_by"]).strip() for j in running_jobs if j.get("claimed_by")}
    worker_job_activity = []
    if worker_names:
        placeholders = ", ".join(["%s"] * len(worker_names))
        worker_job_activity = fetch_all(
            f"""
            SELECT job_id, claimed_by, status, started_at, updated_at, finished_at
            FROM control_job
            WHERE workspace_name = %s 
              AND claimed_by IN ({placeholders})
              AND (updated_at >= NOW() - INTERVAL 1 DAY)
            """,
            (workspace_name, *worker_names),
        )

    active_workers = _active_worker_names(workspace_name)
    now = datetime.now()
    stale_job_ids: list[int] = []
    
    for job in running_jobs:
        claimed_by = str(job.get("claimed_by") or "").strip()
        # Use started_at or fallback to updated_at
        ts_val = job.get("started_at") or job.get("updated_at")
        started_at = _parse_timestamp(ts_val)
        if not started_at:
            continue
            
        worker_has_newer_activity = False
        if claimed_by:
            for candidate in worker_job_activity:
                if str(candidate.get("claimed_by") or "").strip() != claimed_by:
                    continue
                if int(candidate.get("job_id") or 0) == int(job["job_id"]):
                    continue
                # Check for ANY newer activity from this worker
                candidate_ts = (
                    _parse_timestamp(candidate.get("finished_at"))
                    or _parse_timestamp(candidate.get("updated_at"))
                    or _parse_timestamp(candidate.get("started_at"))
                )
                if candidate_ts and candidate_ts > started_at:
                    worker_has_newer_activity = True
                    break
                    
        # A job is stale if:
        # 1. The worker is offline AND has no newer activity
        # 2. OR it has been running longer than the timeout
        if claimed_by and claimed_by in active_workers and not worker_has_newer_activity:
            # Worker is active and hasn't moved on to a new job yet, let it be.
            if (now - started_at).total_seconds() < stale_after_seconds * 2: # Grace period for active workers
                continue
                
        if (now - started_at).total_seconds() < stale_after_seconds:
            continue
            
        stale_job_ids.append(int(job["job_id"]))

    if not stale_job_ids:
        return []

    with db_cursor() as (conn, cursor):
        for job_id in stale_job_ids:
            cursor.execute(
                """
                UPDATE control_job
                SET status = 'failed',
                    error_text = COALESCE(error_text, 'Marked failed after worker heartbeat timeout.'),
                    finished_at = NOW()
                WHERE job_id = %s AND status = 'running'
                """,
                (job_id,),
            )
        conn.commit()
    return stale_job_ids


def list_settings(workspace_name: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM control_setting WHERE 1=1"
    params: list[Any] = []
    if workspace_name:
        query += " AND workspace_name = %s"
        params.append(workspace_name)
    query += " ORDER BY workspace_name ASC, setting_key ASC"
    return fetch_all(query, tuple(params))


@ttl_cache(seconds=60)
def _get_settings_cache(workspace_name: str) -> dict[str, str]:
    """
    Fetches all settings for a workspace and caches them in memory.
    获取工作区的所有设置并将它们缓存在内存中。
    """
    rows = fetch_all(
        "SELECT setting_key, setting_value FROM control_setting WHERE workspace_name = %s",
        (workspace_name,),
    )
    return {r["setting_key"]: str(r["setting_value"]) for r in rows}


def get_setting(workspace_name: str, setting_key: str, default: Any | None = None) -> Any:
    """
    Retrieves a setting value from the memory cache or the database.
    从内存缓存或数据库中检索设置值。
    """
    try:
        cache = _get_settings_cache(workspace_name)
        if setting_key in cache:
            text = cache[setting_key].strip()
            if not text:
                return default
            try:
                return json.loads(text)
            except Exception:
                return text
    except Exception as e:
        logger.warning("Settings cache lookup failed: %s. Falling back to DB.", e)

    # Fallback to direct DB query if cache fails or key missing
    rows = fetch_all(
        """
        SELECT setting_value
        FROM control_setting
        WHERE workspace_name = %s AND setting_key = %s
        LIMIT 1
        """,
        (workspace_name, setting_key),
    )
    if not rows:
        return default
    value = rows[0].get("setting_value")
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return text


def _get_setting_text(workspace_name: str, setting_key: str) -> str | None:
    """
    Internal helper to get raw setting text from cache or DB.
    用于从缓存或数据库获取原始设置文本的内部辅助函数。
    """
    try:
        cache = _get_settings_cache(workspace_name)
        if setting_key in cache:
            return cache[setting_key]
    except Exception:
        pass

    rows = fetch_all(
        """
        SELECT setting_value
        FROM control_setting
        WHERE workspace_name = %s AND setting_key = %s
        LIMIT 1
        """,
        (workspace_name, setting_key),
    )
    if not rows:
        return None
    value = rows[0].get("setting_value")
    if value is None:
        return None
    return str(value)


def _coerce_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _default_ingestion_source_name_for_mode(mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized == "db":
        return "historical_db_backfill"
    return "third_party"


def seed_settings_from_env(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME):
    """
    Seeds the control_setting table with values from environment variables/file if not already present.
    如果数据库中不存在，则使用环境变量或文件中的值填充 control_setting 表。
    """
    from addressforge.core.config import (
        SALT,
        ADDRESSFORGE_PORT,
        ADDRESSFORGE_CONSOLE_PORT,
        ADDRESSFORGE_INGESTION_BATCH_LIST_OVERRIDE,
        ADDRESSFORGE_INGESTION_API_TOKEN,
        MYSQL_CONFIG
    )
    
    # Map of setting keys to current config values
    mappings = {
        "env.TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "env.API_TOKEN": ADDRESSFORGE_INGESTION_API_TOKEN or os.getenv("API_TOKEN", ""),
        "env.SALT": SALT,
        "env.AGENT_API_BASE_URL": os.getenv("AGENT_API_BASE_URL", "http://localhost:9000"),
        "env.ADDRESSFORGE_INGESTION_BATCH_LIST_OVERRIDE": ADDRESSFORGE_INGESTION_BATCH_LIST_OVERRIDE,
        "env.ADDRESSFORGE_PORT": ADDRESSFORGE_PORT,
        "env.ADDRESSFORGE_CONSOLE_PORT": ADDRESSFORGE_CONSOLE_PORT,
        "env.MYSQL_HOST": MYSQL_CONFIG["host"],
        "env.MYSQL_USER": MYSQL_CONFIG["user"],
        "env.MYSQL_PASSWORD": MYSQL_CONFIG["password"],
        "env.MYSQL_DATABASE": MYSQL_CONFIG["database"],
    }
    
    for key, val in mappings.items():
        if val is not None and get_setting(workspace_name, key) is None:
            logger.info("Seeding DB setting %s from environment default.", key)
            set_setting(workspace_name, key, val)


def get_ingestion_runtime_config(workspace_name: str) -> dict[str, Any]:
    def _resolve_setting_text(setting_key: str, default: str) -> str:
        text = _get_setting_text(workspace_name, setting_key)
        if text is None:
            return default
        return text.strip()

    mode = str(get_setting(workspace_name, "ingestion.mode", ADDRESSFORGE_INGESTION_MODE) or ADDRESSFORGE_INGESTION_MODE).strip().lower()
    source_name = str(get_setting(workspace_name, "ingestion.source_name", ADDRESSFORGE_INGESTION_SOURCE_NAME) or ADDRESSFORGE_INGESTION_SOURCE_NAME).strip()
    return {
        "mode": mode if mode in {"api", "db"} else "api",
        "source_name": source_name or ADDRESSFORGE_INGESTION_SOURCE_NAME,
        "api": {
            "batch_size": _coerce_positive_int(
                get_setting(workspace_name, "ingestion.api.batch_size", ADDRESSFORGE_INGESTION_API_BATCH_SIZE),
                ADDRESSFORGE_INGESTION_API_BATCH_SIZE,
            ),
        },
        "db": {
            "batch_size": _coerce_positive_int(
                get_setting(workspace_name, "ingestion.db.batch_size", ADDRESSFORGE_INGESTION_DB_BATCH_SIZE),
                ADDRESSFORGE_INGESTION_DB_BATCH_SIZE,
            ),
            "table": _resolve_setting_text("ingestion.db.table", ADDRESSFORGE_INGESTION_DB_TABLE),
            "cursor_column": _resolve_setting_text("ingestion.db.cursor_column", ADDRESSFORGE_INGESTION_DB_CURSOR_COLUMN),
            "tiebreaker_column": _resolve_setting_text("ingestion.db.tiebreaker_column", ADDRESSFORGE_INGESTION_DB_TIEBREAKER_COLUMN),
            "external_id_column": _resolve_setting_text("ingestion.db.external_id_column", ADDRESSFORGE_INGESTION_DB_EXTERNAL_ID_COLUMN),
            "raw_address_column": _resolve_setting_text("ingestion.db.raw_address_column", ADDRESSFORGE_INGESTION_DB_RAW_ADDRESS_COLUMN),
            "city_column": _resolve_setting_text("ingestion.db.city_column", ADDRESSFORGE_INGESTION_DB_CITY_COLUMN),
            "province_column": _resolve_setting_text("ingestion.db.province_column", ADDRESSFORGE_INGESTION_DB_PROVINCE_COLUMN),
            "postal_code_column": _resolve_setting_text("ingestion.db.postal_code_column", ADDRESSFORGE_INGESTION_DB_POSTAL_CODE_COLUMN),
            "latitude_column": _resolve_setting_text("ingestion.db.latitude_column", ADDRESSFORGE_INGESTION_DB_LATITUDE_COLUMN),
            "longitude_column": _resolve_setting_text("ingestion.db.longitude_column", ADDRESSFORGE_INGESTION_DB_LONGITUDE_COLUMN),
        },
    }


def update_ingestion_runtime_config(workspace_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("mode") or "").strip().lower()
    if mode not in {"api", "db"}:
        raise ValueError("ingestion mode must be 'api' or 'db'")
    raw_source_name = str(payload.get("source_name") or "").strip()
    default_source_name = _default_ingestion_source_name_for_mode(mode)
    if not raw_source_name:
        resolved_source_name = default_source_name
    elif mode == "api" and raw_source_name == "historical_db_backfill":
        resolved_source_name = default_source_name
    elif mode == "db" and raw_source_name == "third_party":
        resolved_source_name = default_source_name
    else:
        resolved_source_name = raw_source_name
    updates: dict[str, Any] = {
        "ingestion.mode": mode,
        "ingestion.source_name": resolved_source_name,
    }
    api_payload = payload.get("api") if isinstance(payload.get("api"), dict) else {}
    db_payload = payload.get("db") if isinstance(payload.get("db"), dict) else {}
    if "batch_size" in api_payload:
        updates["ingestion.api.batch_size"] = _coerce_positive_int(api_payload.get("batch_size"), ADDRESSFORGE_INGESTION_API_BATCH_SIZE)
    if "batch_size" in db_payload:
        updates["ingestion.db.batch_size"] = _coerce_positive_int(db_payload.get("batch_size"), ADDRESSFORGE_INGESTION_DB_BATCH_SIZE)
    db_field_keys = {
        "table": "ingestion.db.table",
        "cursor_column": "ingestion.db.cursor_column",
        "tiebreaker_column": "ingestion.db.tiebreaker_column",
        "external_id_column": "ingestion.db.external_id_column",
        "raw_address_column": "ingestion.db.raw_address_column",
        "city_column": "ingestion.db.city_column",
        "province_column": "ingestion.db.province_column",
        "postal_code_column": "ingestion.db.postal_code_column",
        "latitude_column": "ingestion.db.latitude_column",
        "longitude_column": "ingestion.db.longitude_column",
    }
    for input_key, setting_key in db_field_keys.items():
        if input_key in db_payload:
            updates[setting_key] = str(db_payload.get(input_key) or "").strip()
    for setting_key, value in updates.items():
        set_setting(workspace_name, setting_key, value)
    return get_ingestion_runtime_config(workspace_name)


def build_ingestion_provider_from_runtime_config(workspace_name: str, *, mode: str | None = None, source_name: str | None = None):
    config = get_ingestion_runtime_config(workspace_name)
    resolved_mode = (mode or config["mode"] or "api").strip().lower()
    resolved_source_name = str(source_name or config["source_name"] or ADDRESSFORGE_INGESTION_SOURCE_NAME).strip()
    if resolved_mode == "api":
        return ApiIngestionProvider(source_name=resolved_source_name)
    if resolved_mode == "db":
        db_cfg = config["db"]
        return DatabaseIngestionProvider(
            host=ADDRESSFORGE_INGESTION_DB_HOST,
            user=ADDRESSFORGE_INGESTION_DB_USER,
            password=ADDRESSFORGE_INGESTION_DB_PASSWORD,
            database=ADDRESSFORGE_INGESTION_DB_NAME,
            table=str(db_cfg.get("table") or ADDRESSFORGE_INGESTION_DB_TABLE),
            cursor_column=str(db_cfg.get("cursor_column") or ADDRESSFORGE_INGESTION_DB_CURSOR_COLUMN),
            tie_breaker_column=str(db_cfg.get("tiebreaker_column") or ADDRESSFORGE_INGESTION_DB_TIEBREAKER_COLUMN),
            external_id_column=str(db_cfg.get("external_id_column") or ADDRESSFORGE_INGESTION_DB_EXTERNAL_ID_COLUMN),
            raw_address_column=str(db_cfg.get("raw_address_column") or ADDRESSFORGE_INGESTION_DB_RAW_ADDRESS_COLUMN),
            city_column=str(db_cfg.get("city_column") or ""),
            province_column=str(db_cfg.get("province_column") or ""),
            postal_code_column=str(db_cfg.get("postal_code_column") or ADDRESSFORGE_INGESTION_DB_POSTAL_CODE_COLUMN),
            latitude_column=str(db_cfg.get("latitude_column") or ADDRESSFORGE_INGESTION_DB_LATITUDE_COLUMN),
            longitude_column=str(db_cfg.get("longitude_column") or ADDRESSFORGE_INGESTION_DB_LONGITUDE_COLUMN),
            source_name=resolved_source_name,
        )
    return resolve_ingestion_provider(resolved_mode)


def list_jobs(
    workspace_name: str,
    status: str | None = None,
    job_kind: str | None = None,
    limit: int = 10,
    page: int = 1,
) -> list[dict[str, Any]]:
    """
    Lists jobs, prioritizing running and then queued jobs.
    列出任务，优先显示正在运行和排队的任务。
    """
    reconcile_stale_running_jobs(workspace_name)
    offset = (page - 1) * limit
    query = "SELECT * FROM control_job WHERE workspace_name = %s"
    params: list[Any] = [workspace_name]
    if status:
        query += " AND status = %s"
        params.append(status)
    if job_kind:
        query += " AND job_kind = %s"
        params.append(job_kind)
    rows = fetch_all(query, tuple(params))
    active_workers = _active_worker_names(workspace_name)
    now = datetime.now()
    for row in rows:
        claimed_by = str(row.get("claimed_by") or "").strip()
        if row.get("status") == "running" and claimed_by and claimed_by not in active_workers:
            last_touch = _parse_timestamp(row.get("updated_at")) or _parse_timestamp(row.get("started_at"))
            stale_seconds = (now - last_touch).total_seconds() if last_touch else None
            row["display_status"] = "stale_running"
            row["is_stale_running"] = True
            row["stale_for_seconds"] = int(stale_seconds) if stale_seconds is not None else None
        else:
            row["display_status"] = row.get("status")
            row["is_stale_running"] = False
            row["stale_for_seconds"] = None

    def _sort_bucket(item: dict[str, Any]) -> int:
        display_status = str(item.get("display_status") or item.get("status") or "")
        if display_status == "running":
            return 0
        if display_status == "queued":
            return 1
        if display_status == "stale_running":
            return 2
        return 3

    def _sort_timestamp(item: dict[str, Any]) -> datetime:
        return (
            _parse_timestamp(item.get("updated_at"))
            or _parse_timestamp(item.get("started_at"))
            or _parse_timestamp(item.get("created_at"))
            or datetime.min
        )

    rows.sort(key=lambda item: (_sort_bucket(item), -_sort_timestamp(item).timestamp() if _sort_timestamp(item) != datetime.min else float("inf")))
    return rows[offset: offset + limit]


def set_setting(workspace_name: str, setting_key: str, setting_value: Any) -> dict[str, Any]:
    if isinstance(setting_value, (dict, list)):
        raw_value = json.dumps(setting_value, ensure_ascii=False)
    elif isinstance(setting_value, bool):
        raw_value = "true" if setting_value else "false"
    elif setting_value is None:
        raw_value = ""
    else:
        raw_value = str(setting_value)
    with db_cursor() as (conn, cursor):
        cursor.execute(
            """
            INSERT INTO control_setting (workspace_name, setting_key, setting_value)
            VALUES (%s, %s, %s) AS new_row
            ON DUPLICATE KEY UPDATE
                setting_value = new_row.setting_value,
                updated_at = NOW()
            """,
            (workspace_name, setting_key, raw_value),
        )
        conn.commit()
    
    # Invalidate settings cache
    # 使设置缓存失效
    try:
        _get_settings_cache.clear_cache()
    except Exception:
        pass
        
    return {
        "workspace_name": workspace_name,
        "setting_key": setting_key,
        "setting_value": setting_value,
    }


def _claim_job_row(worker_name: str, workspace_name: str | None = None) -> dict[str, Any] | None:
    query = """
        SELECT *
        FROM control_job
        WHERE status = 'queued'
    """
    params: list[Any] = []
    if workspace_name:
        query += " AND workspace_name = %s"
        params.append(workspace_name)
    query += " ORDER BY priority DESC, created_at ASC, job_id ASC LIMIT 1 FOR UPDATE"
    with transaction_cursor(dictionary=True) as (conn, cursor):
        cursor.execute(query, tuple(params))
        row = cursor.fetchone()
        if not row:
            return None
        cursor.execute(
            """
            UPDATE control_job
            SET status = 'running',
                claimed_by = %s,
                claimed_at = NOW(),
                started_at = NOW()
            WHERE job_id = %s
            """,
            (worker_name, row["job_id"]),
        )
        row["status"] = "running"
        row["claimed_by"] = worker_name
        row["claimed_at"] = datetime.utcnow().isoformat(sep=" ")
        row["started_at"] = row["claimed_at"]
        return row


def claim_next_job(worker_name: str, workspace_name: str | None = None) -> dict[str, Any] | None:
    return _claim_job_row(worker_name=worker_name, workspace_name=workspace_name)


def _store_job_result(
    job_id: int,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    error_text: str | None = None,
    etl_run_id: int | None = None,
) -> None:
    with db_cursor() as (conn, cursor):
        cursor.execute(
            """
            UPDATE control_job
            SET status = %s,
                result_json = COALESCE(%s, result_json),
                error_text = COALESCE(%s, error_text),
                etl_run_id = COALESCE(%s, etl_run_id),
                finished_at = NOW()
            WHERE job_id = %s
            """,
            (status, _json_or_none(result), error_text, etl_run_id, job_id),
        )
        conn.commit()


def _run_ingestion_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload_json")
    payload_data = json.loads(payload) if payload else {}
    workspace_name = str(job["workspace_name"] or ADDRESSFORGE_WORKSPACE_NAME)
    runtime_config = get_ingestion_runtime_config(workspace_name)
    mode = str(payload_data.get("mode") or runtime_config["mode"] or ADDRESSFORGE_INGESTION_MODE or "api").strip().lower()
    default_batch_size = int(runtime_config["db"]["batch_size"] if mode == "db" else runtime_config["api"]["batch_size"])
    batch_size = _coerce_positive_int(payload_data.get("batch_size"), default_batch_size)
    source_name = str(payload_data.get("source_name") or runtime_config["source_name"] or ADDRESSFORGE_INGESTION_SOURCE_NAME).strip()
    cursor_override = payload_data.get("cursor_override")
    attempt = int(payload_data.get("retry_count") or 0)
    service = IngestionService(
        provider=build_ingestion_provider_from_runtime_config(workspace_name, mode=mode, source_name=source_name),
        source_name=source_name,
        workspace_name=workspace_name,
    )
    result = asdict(service.run_once(batch_size=batch_size, cursor_override=cursor_override, attempt=attempt))
    followup_job: dict[str, Any] | None = None
    if bool(result.get("has_more")) and result.get("next_cursor"):
        followup_job = create_job(
            workspace_name=workspace_name,
            job_kind="ingestion_once",
            payload={
                "workspace_name": workspace_name,
                "mode": mode,
                "batch_size": batch_size,
                "source_name": source_name,
                "cursor_override": result.get("next_cursor"),
                "retry_count": 0,
                "triggered_by": "auto_followup_after_ingestion_page",
                "source_job_id": job.get("job_id"),
            },
            requested_by="system",
            priority=int(job.get("priority") or 0),
        )
    elif int(result.get("records_ingested") or 0) > 0:
        auto_clean_enabled = get_setting(workspace_name, "pipeline.auto_clean.enabled", True)
        if _truthy_setting(auto_clean_enabled):
            followup_job = create_job(
                workspace_name=workspace_name,
                job_kind="cleaning_once",
                payload={
                    "workspace_name": workspace_name,
                    "batch_size": batch_size,
                    "triggered_by": "auto_followup_after_ingestion",
                    "source_job_id": job.get("job_id"),
                },
                requested_by="system",
                priority=-1,
            )
    set_setting(workspace_name, "ingestion.retry_job_id", "")
    return {
        "job_kind": job["job_kind"],
        "workspace_name": job["workspace_name"],
        "mode": mode,
        "batch_size": batch_size,
        "source_name": source_name,
        "retry_count": attempt,
        "result": result,
        "followup_job": followup_job,
    }


def _schedule_ingestion_retry(job: dict[str, Any], error_text: str) -> dict[str, Any] | None:
    payload_raw = job.get("payload_json")
    payload = json.loads(payload_raw) if payload_raw else {}
    workspace_name = str(job.get("workspace_name") or ADDRESSFORGE_WORKSPACE_NAME)
    max_attempts = int(get_setting(workspace_name, "ingestion.retry.max_attempts", 3) or 3)
    current_attempt = int(payload.get("retry_count") or 0)
    next_attempt = current_attempt + 1
    if next_attempt >= max_attempts:
        return None
    retry_payload = dict(payload)
    retry_payload["retry_count"] = next_attempt
    retry_payload["retry_reason"] = error_text
    if not retry_payload.get("cursor_override"):
        failed_cursor = get_setting(workspace_name, "ingestion.last_failed_cursor", "")
        if failed_cursor:
            retry_payload["cursor_override"] = failed_cursor
    retry_job = create_job(
        workspace_name=workspace_name,
        job_kind="ingestion_once",
        payload=retry_payload,
        requested_by="system",
        priority=int(job.get("priority") or 0),
    )
    set_setting(workspace_name, "ingestion.alert_status", "retrying")
    set_setting(workspace_name, "ingestion.retry_job_id", retry_job.get("job_id"))
    return retry_job


from addressforge.pipelines.training_pipeline import run_training_pipeline

def _run_training_job(job: dict[str, Any]) -> dict[str, Any]:
    """
    Executes the training job via the unified training pipeline.
    通过统一的训练流水线执行训练任务。
    """
    payload = job.get("payload_json")
    payload_data = json.loads(payload) if payload else {}
    workspace_name = str(payload_data.get("workspace_name") or job["workspace_name"] or ADDRESSFORGE_WORKSPACE_NAME)
    model_name = str(payload_data.get("model_name") or ADDRESSFORGE_MODEL_NAME)
    model_version = payload_data.get("model_version") # Let pipeline auto-generate if None / 如果为 None，则让流水线自动生成
    dataset_name = str(payload_data.get("dataset_name") or "default_training_set")
    
    # Use the unified training pipeline which handles the end-to-end process
    # 使用统一的训练流水线来处理端到端过程
    result = run_training_pipeline(
        workspace_name=workspace_name,
        model_name=model_name,
        model_version=model_version,
    )
    
    # Extract the actual version used or generated by the pipeline
    # 提取流水线实际使用或生成的版本
    actual_model_version = result.get("model_version") or model_version
    
    followup_job: dict[str, Any] | None = None
    auto_eval_enabled = get_setting(workspace_name, "pipeline.auto_eval.enabled", True)
    if _truthy_setting(auto_eval_enabled):
        followup_job = create_job(
            workspace_name=workspace_name,
            job_kind="evaluation_once",
            payload={
                "workspace_name": workspace_name,
                "model_name": model_name,
                "model_version": actual_model_version,
                "dataset_name": dataset_name,
                "triggered_by": "auto_followup_after_training",
                "source_job_id": job.get("job_id"),
            },
            requested_by="system",
            priority=-1,
        )
    return {
        "job_kind": job["job_kind"],
        "workspace_name": workspace_name,
        "model_name": model_name,
        "model_version": actual_model_version,
        "dataset_name": dataset_name,
        "result": result,
        "followup_job": followup_job,
    }


def _run_evaluation_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload_json")
    payload_data = json.loads(payload) if payload else {}
    workspace_name = str(payload_data.get("workspace_name") or job["workspace_name"] or ADDRESSFORGE_WORKSPACE_NAME)
    model_name = str(payload_data.get("model_name") or ADDRESSFORGE_MODEL_NAME)
    model_version = str(payload_data.get("model_version") or ADDRESSFORGE_MODEL_VERSION)
    dataset_name = str(payload_data.get("dataset_name") or "default_training_set")
    result = run_baseline_evaluation(
        workspace_name=workspace_name,
        model_name=model_name,
        model_version=model_version,
        dataset_name=dataset_name,
    )
    followup_job: dict[str, Any] | None = None
    auto_shadow_enabled = get_setting(workspace_name, "pipeline.auto_shadow.enabled", True)
    if _truthy_setting(auto_shadow_enabled):
        followup_job = create_job(
            workspace_name=workspace_name,
            job_kind="shadow_once",
            payload={
                "workspace_name": workspace_name,
                "model_name": model_name,
                "model_version": model_version,
                "dataset_name": dataset_name,
                "triggered_by": "auto_followup_after_evaluation",
                "source_job_id": job.get("job_id"),
            },
            requested_by="system",
            priority=-1,
        )
    return {
        "job_kind": job["job_kind"],
        "workspace_name": workspace_name,
        "model_name": model_name,
        "model_version": model_version,
        "dataset_name": dataset_name,
        "result": result,
        "followup_job": followup_job,
    }


def _run_shadow_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload_json")
    payload_data = json.loads(payload) if payload else {}
    workspace_name = str(payload_data.get("workspace_name") or job["workspace_name"] or ADDRESSFORGE_WORKSPACE_NAME)
    model_name = str(payload_data.get("model_name") or ADDRESSFORGE_MODEL_NAME)
    model_version = str(payload_data.get("model_version") or ADDRESSFORGE_MODEL_VERSION)
    dataset_name = str(payload_data.get("dataset_name") or "default_training_set")
    result = run_baseline_shadow(
        workspace_name=workspace_name,
        model_name=model_name,
        model_version=model_version,
        dataset_name=dataset_name,
    )
    followup_jobs: list[dict[str, Any]] = []
    promotion_result: dict[str, Any] | None = None
    auto_active_learning_enabled = get_setting(workspace_name, "pipeline.auto_active_learning.enabled", True)
    if _truthy_setting(auto_active_learning_enabled):
        followup_job = create_job(
            workspace_name=workspace_name,
            job_kind="active_learning_once",
            payload={
                "workspace_name": workspace_name,
                "dataset_name": dataset_name,
                "triggered_by": "auto_followup_after_shadow",
                "source_job_id": job.get("job_id"),
            },
            requested_by="system",
            priority=-1,
        )
        followup_jobs.append(followup_job)
    auto_promote_enabled = get_setting(workspace_name, "pipeline.auto_promote.enabled", False)
    min_delta = float(get_setting(workspace_name, "pipeline.auto_promote.min_delta", 0.0) or 0.0)
    shadow_recommended = bool(result.get("promote_recommended"))
    if _truthy_setting(auto_promote_enabled) and shadow_recommended and float(result.get("score_delta") or 0.0) >= min_delta:
        promotion_result = promote_model(
            workspace_name=workspace_name,
            model_name=model_name,
            model_version=model_version,
            notes=f"auto-promoted after shadow delta={result.get('score_delta')}",
        )
    return {
        "job_kind": job["job_kind"],
        "workspace_name": workspace_name,
        "model_name": model_name,
        "model_version": model_version,
        "dataset_name": dataset_name,
        "result": result,
        "followup_job": followup_jobs[0] if followup_jobs else None,
        "followup_jobs": followup_jobs,
        "promotion_result": promotion_result,
    }


def _run_gold_freeze_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload_json")
    payload_data = json.loads(payload) if payload else {}
    workspace_name = str(payload_data.get("workspace_name") or job["workspace_name"] or ADDRESSFORGE_WORKSPACE_NAME)
    gold_set_version = str(payload_data.get("gold_set_version") or "gold_v1")
    split_version = str(payload_data.get("split_version") or "v1")
    label_source_filter = str(payload_data.get("label_source_filter") or "human")
    task_type = payload_data.get("task_type")
    result = freeze_gold_set(
        workspace_name=workspace_name,
        gold_set_version=gold_set_version,
        split_version=split_version,
        label_source_filter=label_source_filter,
        task_type=task_type,
        notes=payload_data.get("notes"),
    )
    return {
        "job_kind": job["job_kind"],
        "workspace_name": workspace_name,
        "result": result,
    }


def _run_active_learning_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload_json")
    payload_data = json.loads(payload) if payload else {}
    workspace_name = str(payload_data.get("workspace_name") or job["workspace_name"] or ADDRESSFORGE_WORKSPACE_NAME)
    limit = int(payload_data.get("limit") or 250)
    confidence_threshold = float(payload_data.get("confidence_threshold") or 0.55)
    result = seed_active_learning_queue(
        workspace_name=workspace_name,
        limit=limit,
        confidence_threshold=confidence_threshold,
    )
    return {
        "job_kind": job["job_kind"],
        "workspace_name": workspace_name,
        "result": result,
    }


def _run_reference_import_job(job: dict[str, Any]) -> dict[str, Any]:
    workspace_name = str(job.get("workspace_name") or ADDRESSFORGE_WORKSPACE_NAME)
    payload_raw = job.get("payload_json")
    payload = json.loads(payload_raw) if payload_raw else {}
    csv_path = payload.get("csv_path") if isinstance(payload, dict) else None
    batch_size = int(payload.get("batch_size") or 5000) if isinstance(payload, dict) else 5000
    result = ExternalReferenceImportService().run(
        csv_path=csv_path,
        batch_size=batch_size,
        workspace_name=workspace_name,
    )
    return {
        "job_kind": job["job_kind"],
        "workspace_name": workspace_name,
        "csv_path": csv_path,
        "batch_size": batch_size,
        "result": result,
    }


def _run_workspace_export_job(job: dict[str, Any]) -> dict[str, Any]:
    workspace_name = str(job.get("workspace_name") or ADDRESSFORGE_WORKSPACE_NAME)
    payload_raw = job.get("payload_json")
    payload = json.loads(payload_raw) if payload_raw else {}
    export_root = payload.get("export_root") if isinstance(payload, dict) else None
    result = export_workspace_snapshot(workspace_name=workspace_name, export_root=export_root)
    return {
        "job_kind": job["job_kind"],
        "workspace_name": workspace_name,
        "export_root": export_root,
        "result": result,
    }


def _run_cleaning_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload_json")
    payload_data = json.loads(payload) if payload else {}
    workspace_name = str(payload_data.get("workspace_name") or job["workspace_name"] or ADDRESSFORGE_WORKSPACE_NAME)
    batch_size = int(payload_data.get("batch_size") or 1000)
    from addressforge.pipelines.cleaning import run_cleaning_once

    result = run_cleaning_once(workspace_name=workspace_name, batch_size=batch_size)
    followup_job: dict[str, Any] | None = None
    if bool(result.get("has_more")) and result.get("next_raw_id"):
        followup_job = create_job(
            workspace_name=workspace_name,
            job_kind="cleaning_once",
            payload={
                "workspace_name": workspace_name,
                "batch_size": batch_size,
                "triggered_by": "auto_followup_after_cleaning_page",
                "source_job_id": job.get("job_id"),
            },
            requested_by="system",
            priority=int(job.get("priority") or 0),
        )
    else:
        auto_train_enabled = get_setting(workspace_name, "pipeline.auto_train.enabled", False)
        if int(result.get("records_processed") or 0) > 0 and _truthy_setting(auto_train_enabled):
            followup_job = create_job(
                workspace_name=workspace_name,
                job_kind="training_once",
                payload={
                    "workspace_name": workspace_name,
                    "dataset_name": "default_training_set",
                    "triggered_by": "auto_followup_after_cleaning",
                    "source_job_id": job.get("job_id"),
                },
                requested_by="system",
                priority=-1,
            )
    return {
        "job_kind": job["job_kind"],
        "workspace_name": workspace_name,
        "batch_size": batch_size,
        "result": result,
        "followup_job": followup_job,
    }


def _schedule_cleaning_retry(job: dict[str, Any], error_text: str) -> dict[str, Any] | None:
    payload_raw = job.get("payload_json")
    payload = json.loads(payload_raw) if payload_raw else {}
    workspace_name = str(job.get("workspace_name") or ADDRESSFORGE_WORKSPACE_NAME)
    retry_payload = dict(payload)
    retry_payload["triggered_by"] = "auto_retry_after_cleaning_failure"
    retry_payload["retry_reason"] = error_text
    return create_job(
        workspace_name=workspace_name,
        job_kind="cleaning_once",
        payload=retry_payload,
        requested_by="system",
        priority=int(job.get("priority") or 0),
    )


def _run_promote_assets_job(job: dict[str, Any]) -> dict[str, Any]:
    """
    Promotes high-confidence results to canonical assets.
    将高置信度结果提升为标准资产。
    """
    workspace_name = str(job.get("workspace_name") or ADDRESSFORGE_WORKSPACE_NAME)
    from addressforge.services.asset_service import promote_results_to_assets
    result = promote_results_to_assets(workspace_name=workspace_name)
    return {
        "job_kind": "promote_assets_once",
        "workspace_name": workspace_name,
        "result": result
    }

def _run_evolution_job(job: dict[str, Any]) -> dict[str, Any]:
    """
    Executes the full ML evolution cycle via shell script.
    通过 shell 脚本执行完整的 ML 演进周期。
    """
    import subprocess
    from pathlib import Path
    
    # Resolve the absolute path to the script
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "run_evolution_cycle.sh"
    
    if not script_path.exists():
        raise FileNotFoundError(f"Evolution script not found at {script_path}")
        
    logger.info("Starting ML evolution cycle via %s", script_path)
    
    # Run the script and capture output
    result = subprocess.run(
        [str(script_path)],
        capture_output=True,
        text=True,
        check=True
    )
    
    return {
        "status": "success",
        "stdout": result.stdout[-1000:], # Return last 1k chars
        "message": "Full ML evolution cycle completed and services restarted."
    }

def _run_reload_models_job(job: dict[str, Any]) -> dict[str, Any]:
    """
    Instructs the worker to reload all models in memory.
    指示 worker 重载内存中的所有模型。
    """
    logger.info("Worker is hot-reloading models...")
    from addressforge.services.model_service import get_model_service
    from addressforge.services.reranker_service import get_reranker_service
    from addressforge.core.retrieval import get_vector_engine
    
    get_model_service().reload_models()
    get_reranker_service().reload_models()
    get_vector_engine().reload_models()
    
    return {
        "status": "success",
        "message": "Models reloaded in worker process."
    }

def run_job(job: dict[str, Any]) -> dict[str, Any]:
    job_kind = str(job.get("job_kind") or "")
    ensure_etl_run_types()
    run_id = create_run("control_job", notes=f"job_id={job.get('job_id')} kind={job_kind}")
    try:
        if job_kind == "bootstrap_registry":
            result = bootstrap_default_registry()
        elif job_kind == "ingestion_once":
            result = _run_ingestion_job(job)
        elif job_kind == "reference_import_once":
            result = _run_reference_import_job(job)
        elif job_kind == "workspace_export_once":
            result = _run_workspace_export_job(job)
        elif job_kind == "cleaning_once":
            result = _run_cleaning_job(job)
        elif job_kind == "training_once":
            result = _run_training_job(job)
        elif job_kind == "evaluation_once":
            result = _run_evaluation_job(job)
        elif job_kind == "shadow_once":
            result = _run_shadow_job(job)
        elif job_kind == "gold_freeze_once":
            result = _run_gold_freeze_job(job)
        elif job_kind == "active_learning_once":
            result = _run_active_learning_job(job)
        elif job_kind == "promote_assets_once":
            result = _run_promote_assets_job(job)
        elif job_kind == "evolution_once":
            result = _run_evolution_job(job)
        elif job_kind == "reload_models_once":
            result = _run_reload_models_job(job)
        else:
            raise ValueError(f"Unsupported job kind: {job_kind}")
        _store_job_result(job["job_id"], status="succeeded", result=result, etl_run_id=run_id)
        finish_run(run_id, "completed", notes=f"Job {job_kind} (id={job['job_id']}) completed successfully.")
        logger.info("Control job succeeded: job_id=%s kind=%s", job["job_id"], job_kind)
        return result
    except Exception as exc:  # noqa: BLE001
        failure_result: dict[str, Any] | None = None
        if job_kind == "ingestion_once":
            retry_job = _schedule_ingestion_retry(job, str(exc))
            if retry_job:
                failure_result = {
                    "job_kind": job_kind,
                    "workspace_name": job.get("workspace_name"),
                    "retry_job": retry_job,
                }
            else:
                set_setting(str(job.get("workspace_name") or ADDRESSFORGE_WORKSPACE_NAME), "ingestion.retry_job_id", "")
        elif job_kind == "cleaning_once":
            retry_job = _schedule_cleaning_retry(job, str(exc))
            failure_result = {
                "job_kind": job_kind,
                "workspace_name": job.get("workspace_name"),
                "retry_job": retry_job,
            }
        _store_job_result(job["job_id"], status="failed", result=failure_result, error_text=str(exc), etl_run_id=run_id)
        finish_run(run_id, "failed", notes=dumps_payload({"error": str(exc)}))
        logger.exception("Control job failed: job_id=%s kind=%s", job.get("job_id"), job_kind)
        return failure_result or {"status": "failed", "error": str(exc)}
