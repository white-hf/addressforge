from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.core.utils import logger

from .jobs import (
    claim_next_job,
    create_job,
    get_setting,
    list_jobs,
    run_job,
    set_setting,
)


@dataclass(frozen=True)
class WorkerState:
    worker_name: str
    workspace_name: str
    poll_interval_seconds: int


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class ControlWorker:
    def __init__(
        self,
        workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
        worker_name: str | None = None,
        poll_interval_seconds: int = 5,
    ) -> None:
        self.workspace_name = workspace_name
        self.worker_name = worker_name or os.getenv("ADDRESSFORGE_WORKER_NAME", f"worker-{os.getpid()}")
        self.poll_interval_seconds = max(1, int(poll_interval_seconds))

    def state(self) -> WorkerState:
        return WorkerState(
            worker_name=self.worker_name,
            workspace_name=self.workspace_name,
            poll_interval_seconds=self.poll_interval_seconds,
        )

    def _continuous_mode_enabled(self) -> bool:
        value = get_setting(self.workspace_name, "continuous_mode.enabled", False)
        return _truthy(value)

    def _continuous_interval(self) -> int:
        value = get_setting(self.workspace_name, "continuous_mode.interval_seconds", self.poll_interval_seconds)
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return self.poll_interval_seconds

    def _seed_continuous_ingestion(self) -> dict[str, Any] | None:
        if not self._continuous_mode_enabled():
            return None
        queue = list_jobs(self.workspace_name, status="queued", job_kind="ingestion_once", limit=1)
        running = list_jobs(self.workspace_name, status="running", job_kind="ingestion_once", limit=1)
        if queue or running:
            return None
        last_trigger_at = get_setting(self.workspace_name, "continuous_mode.last_trigger_at", None)
        interval_seconds = self._continuous_interval()
        if last_trigger_at:
            try:
                last_ts = time.mktime(time.strptime(str(last_trigger_at)[:19], "%Y-%m-%d %H:%M:%S"))
                if time.time() - last_ts < interval_seconds:
                    return None
            except Exception:
                pass
        payload = {
            "mode": os.getenv("ADDRESSFORGE_INGESTION_MODE", "api"),
            "batch_size": int(os.getenv("ADDRESSFORGE_INGESTION_API_BATCH_SIZE", "1000")),
            "source_name": os.getenv("ADDRESSFORGE_INGESTION_SOURCE_NAME", "third_party"),
        }
        alert_status = str(get_setting(self.workspace_name, "ingestion.alert_status", "ok") or "ok")
        failed_cursor = get_setting(self.workspace_name, "ingestion.last_failed_cursor", "")
        if alert_status == "error" and failed_cursor:
            payload["cursor_override"] = failed_cursor
            payload["retry_count"] = 0
        job = create_job(
            workspace_name=self.workspace_name,
            job_kind="ingestion_once",
            payload=payload,
            requested_by=self.worker_name,
            priority=0,
        )
        set_setting(self.workspace_name, "continuous_mode.last_trigger_at", time.strftime("%Y-%m-%d %H:%M:%S"))
        logger.info("Seeded ingestion job for continuous mode: %s", job.get("job_id"))
        return job

    def poll_once(self) -> dict[str, Any] | None:
        self._seed_continuous_ingestion()
        job = claim_next_job(worker_name=self.worker_name, workspace_name=self.workspace_name)
        if not job:
            return None
        logger.info(
            "Claimed control job: job_id=%s kind=%s workspace=%s",
            job.get("job_id"),
            job.get("job_kind"),
            job.get("workspace_name"),
        )
        return run_job(job)

    def run_forever(self) -> None:
        logger.info(
            "Control worker started: worker=%s workspace=%s poll_interval=%s",
            self.worker_name,
            self.workspace_name,
            self.poll_interval_seconds,
        )
        while True:
            try:
                result = self.poll_once()
                if result is None:
                    time.sleep(self.poll_interval_seconds)
                else:
                    time.sleep(0.2)
            except KeyboardInterrupt:
                logger.info("Control worker stopped by user")
                break
            except Exception as exc:  # noqa: BLE001
                logger.exception("Control worker error: %s", exc)
                time.sleep(self.poll_interval_seconds)


def run_control_worker() -> None:
    workspace_name = os.getenv("ADDRESSFORGE_WORKSPACE_NAME", ADDRESSFORGE_WORKSPACE_NAME)
    poll_interval = int(os.getenv("ADDRESSFORGE_WORKER_POLL_INTERVAL_SECONDS", "5"))
    worker = ControlWorker(workspace_name=workspace_name, poll_interval_seconds=poll_interval)
    worker.run_forever()
