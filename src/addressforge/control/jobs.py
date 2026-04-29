from __future__ import annotations

import json
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
    ADDRESSFORGE_INGESTION_MODE,
    ADDRESSFORGE_INGESTION_SOURCE_NAME,
    ADDRESSFORGE_MODEL_NAME,
    ADDRESSFORGE_MODEL_VERSION,
    ADDRESSFORGE_WORKSPACE_NAME,
)
from addressforge.core.utils import logger
from addressforge.ingestion.service import IngestionService
from addressforge.ingestion.providers import resolve_ingestion_provider
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
    "bootstrap_registry",
)
CONTROL_JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")


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


def bootstrap_control_center() -> dict[str, Any]:
    registry = bootstrap_default_registry()
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
        ingested = result.get("result", {}).get("records_ingested") if isinstance(result.get("result"), dict) else None
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


def list_jobs(
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


def count_jobs(workspace_name: str | None = None) -> dict[str, int]:
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


def count_jobs_by_kind(workspace_name: str | None = None) -> dict[str, int]:
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


def list_settings(workspace_name: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM control_setting WHERE 1=1"
    params: list[Any] = []
    if workspace_name:
        query += " AND workspace_name = %s"
        params.append(workspace_name)
    query += " ORDER BY workspace_name ASC, setting_key ASC"
    return fetch_all(query, tuple(params))


def get_setting(workspace_name: str, setting_key: str, default: Any | None = None) -> Any:
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
    mode = str(payload_data.get("mode") or ADDRESSFORGE_INGESTION_MODE or "api")
    batch_size = int(payload_data.get("batch_size") or 1000)
    source_name = str(payload_data.get("source_name") or ADDRESSFORGE_INGESTION_SOURCE_NAME)
    cursor_override = payload_data.get("cursor_override")
    attempt = int(payload_data.get("retry_count") or 0)
    service = IngestionService(
        provider=resolve_ingestion_provider(mode),
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


def _run_training_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload_json")
    payload_data = json.loads(payload) if payload else {}
    workspace_name = str(payload_data.get("workspace_name") or job["workspace_name"] or ADDRESSFORGE_WORKSPACE_NAME)
    model_name = str(payload_data.get("model_name") or ADDRESSFORGE_MODEL_NAME)
    model_version = str(payload_data.get("model_version") or ADDRESSFORGE_MODEL_VERSION)
    dataset_name = str(payload_data.get("dataset_name") or "default_training_set")
    result = run_baseline_training(
        workspace_name=workspace_name,
        model_name=model_name,
        model_version=model_version,
        dataset_name=dataset_name,
    )
    followup_job: dict[str, Any] | None = None
    auto_eval_enabled = get_setting(workspace_name, "pipeline.auto_eval.enabled", True)
    if _truthy_setting(auto_eval_enabled):
        followup_job = create_job(
            workspace_name=workspace_name,
            job_kind="evaluation_once",
            payload={
                "workspace_name": workspace_name,
                "model_name": model_name,
                "model_version": model_version,
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
        "model_version": model_version,
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
        else:
            raise ValueError(f"Unsupported job kind: {job_kind}")
        _store_job_result(job["job_id"], status="succeeded", result=result, etl_run_id=run_id)
        finish_run(run_id, "completed", notes=dumps_payload(result if isinstance(result, dict) else {"result": str(result)}))
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
        raise
