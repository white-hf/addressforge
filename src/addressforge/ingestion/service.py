from __future__ import annotations

import json
import time
from datetime import datetime
from dataclasses import asdict
from typing import Any

from addressforge.core.common import (
    create_run,
    db_cursor,
    dumps_payload,
    executemany_chunked,
    finish_run,
    get_ingestion_cursor,
    set_ingestion_cursor,
)
from addressforge.core.config import ADDRESSFORGE_INGESTION_CURSOR_TYPE, ADDRESSFORGE_INGESTION_SOURCE_NAME
from addressforge.core.utils import logger
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME

from .models import IngestionPage, IngestionRecord, IngestionResult
from .providers import BaseIngestionProvider, resolve_ingestion_provider


RAW_INGEST_TABLE = "raw_address_record"


class IngestionService:
    def __init__(
        self,
        provider: BaseIngestionProvider | None = None,
        target_table: str = RAW_INGEST_TABLE,
        source_name: str = ADDRESSFORGE_INGESTION_SOURCE_NAME,
        cursor_type: str = ADDRESSFORGE_INGESTION_CURSOR_TYPE,
        workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    ) -> None:
        self.provider = provider or resolve_ingestion_provider()
        self.target_table = target_table
        self.source_name = source_name
        self.cursor_type = cursor_type
        self.workspace_name = workspace_name

    def _set_setting(self, key: str, value: Any) -> None:
        raw_value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else (
            "true" if isinstance(value, bool) and value else "false" if isinstance(value, bool) else "" if value is None else str(value)
        )
        with db_cursor() as (conn, cursor):
            cursor.execute(
                """
                INSERT INTO control_setting (workspace_name, setting_key, setting_value)
                VALUES (%s, %s, %s) AS new_row
                ON DUPLICATE KEY UPDATE
                    setting_value = new_row.setting_value,
                    updated_at = NOW()
                """,
                (self.workspace_name, key, raw_value),
            )
            conn.commit()

    def _mark_success(
        self,
        *,
        run_id: int,
        current_cursor: str | None,
        page: IngestionPage,
        ingested: int,
    ) -> None:
        self._set_setting("ingestion.alert_status", "ok")
        self._set_setting("ingestion.last_error", "")
        self._set_setting("ingestion.last_failed_cursor", "")
        self._set_setting("ingestion.consecutive_failures", 0)
        self._set_setting("ingestion.last_success_at", datetime.utcnow().isoformat(sep=" "))
        self._set_setting("ingestion.last_mode", self.provider.__class__.__name__)
        self._set_setting("ingestion.last_source_name", self.source_name)
        self._set_setting(
            "ingestion.last_result",
            {
                "run_id": run_id,
                "source_name": self.source_name,
                "cursor_type": self.cursor_type,
                "current_cursor": current_cursor,
                "next_cursor": page.next_cursor,
                "has_more": page.has_more,
                "records_seen": len(page.records),
                "records_ingested": ingested,
            },
        )
        self._set_setting("ingestion.last_records_seen", len(page.records))
        self._set_setting("ingestion.last_records_ingested", ingested)
        self._set_setting("ingestion.last_next_cursor", page.next_cursor or "")
        self._set_setting("ingestion.last_has_more", page.has_more)

    def _mark_failure(
        self,
        *,
        current_cursor: str | None,
        error_text: str,
        attempt: int = 0,
    ) -> None:
        self._set_setting("ingestion.alert_status", "error")
        self._set_setting("ingestion.last_error", error_text)
        self._set_setting("ingestion.last_failed_cursor", current_cursor or "")
        self._set_setting("ingestion.last_failed_at", datetime.utcnow().isoformat(sep=" "))
        self._set_setting("ingestion.last_retry_attempt", attempt)
        try:
            previous_failures = int(self._get_setting("ingestion.consecutive_failures", 0) or 0)
        except (TypeError, ValueError):
            previous_failures = 0
        self._set_setting("ingestion.consecutive_failures", previous_failures + 1)
        self._set_setting("ingestion.last_mode", self.provider.__class__.__name__)
        self._set_setting("ingestion.last_source_name", self.source_name)

    def _get_setting(self, key: str, default: Any | None = None) -> Any:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT setting_value
                FROM control_setting
                WHERE workspace_name = %s AND setting_key = %s
                LIMIT 1
                """,
                (self.workspace_name, key),
            )
            row = cursor.fetchone()
        if not row:
            return default
        value = row[0] if isinstance(row, tuple) else row.get("setting_value")
        if value is None:
            return default
        text = str(value).strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except Exception:
            return text

    def _retry(self, label: str, func, *args, attempts: int = 3, **kwargs):
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("Ingestion %s failed on attempt %s/%s: %s", label, attempt, attempts, exc)
                if attempt < attempts:
                    time.sleep(min(2.0 * attempt, 5.0))
        if last_exc:
            raise last_exc
        raise RuntimeError(f"Ingestion {label} failed without exception")

    def _upsert_records(self, records: list[IngestionRecord]) -> int:
        if not records:
            return 0
        query = f"""
            INSERT INTO {self.target_table} (
                workspace_name, source_name, external_id, raw_address_text, city, province, postal_code,
                country_code, latitude, longitude, source_cursor, source_payload, is_active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1) AS new_row
            ON DUPLICATE KEY UPDATE
                workspace_name = new_row.workspace_name,
                raw_address_text = new_row.raw_address_text,
                city = new_row.city,
                province = new_row.province,
                postal_code = new_row.postal_code,
                country_code = new_row.country_code,
                latitude = new_row.latitude,
                longitude = new_row.longitude,
                source_cursor = new_row.source_cursor,
                source_payload = new_row.source_payload,
                is_active = 1,
                updated_at = CURRENT_TIMESTAMP
        """
        payload: list[tuple[Any, ...]] = []
        for record in records:
            if not record.external_id or not record.raw_address_text:
                continue
            payload.append(
                (
                    self.workspace_name,
                    record.source_name,
                    record.external_id,
                    record.raw_address_text,
                    record.city,
                    record.province,
                    record.postal_code,
                    record.country_code,
                    record.latitude,
                    record.longitude,
                    record.cursor_value,
                    dumps_payload({**record.source_payload, "source_name": record.source_name}),
                )
            )
        if not payload:
            return 0
        with db_cursor() as (conn, cursor):
            executemany_chunked(cursor, query, payload, chunk_size=500)
            conn.commit()
        return len(payload)

    def run_once(self, batch_size: int = 1000, cursor_override: str | None = None, attempt: int = 0) -> IngestionResult:
        run_id = create_run("ingestion", notes=f"{self.source_name} batch_size={batch_size}")
        current_cursor = cursor_override
        try:
            if current_cursor in (None, ""):
                current_cursor = get_ingestion_cursor(self.source_name, self.cursor_type, self.workspace_name)
            page: IngestionPage = self._retry("fetch_page", self.provider.fetch_page, current_cursor, batch_size)
            ingested = self._retry("upsert_records", self._upsert_records, page.records)
            if page.next_cursor:
                set_ingestion_cursor(self.source_name, self.cursor_type, str(page.next_cursor), self.workspace_name)
            notes = dumps_payload(
                {
                    "source_name": self.source_name,
                    "cursor_type": self.cursor_type,
                    "current_cursor": current_cursor,
                    "next_cursor": page.next_cursor,
                    "has_more": page.has_more,
                    "records_seen": len(page.records),
                    "records_ingested": ingested,
                }
            )
            finish_run(run_id, "completed", notes=notes)
            self._set_setting("ingestion.last_run_at", datetime.utcnow().isoformat(sep=" "))
            self._mark_success(run_id=run_id, current_cursor=current_cursor, page=page, ingested=ingested)
            logger.info(
                "Ingestion run %s completed: source=%s seen=%s ingested=%s next_cursor=%s",
                run_id,
                self.source_name,
                len(page.records),
                ingested,
                page.next_cursor,
            )
            return IngestionResult(
                run_id=run_id,
                source_name=self.source_name,
                records_seen=len(page.records),
                records_ingested=ingested,
                next_cursor=page.next_cursor,
                has_more=page.has_more,
                mode=self.provider.__class__.__name__,
            )
        except Exception as exc:
            self._mark_failure(current_cursor=current_cursor, error_text=str(exc), attempt=attempt)
            finish_run(run_id, "failed", notes=dumps_payload({"error": str(exc), "source_name": self.source_name}))
            raise


def run_default_ingestion(batch_size: int = 1000, mode: str | None = None, cursor_override: str | None = None, attempt: int = 0) -> dict[str, Any]:
    service = IngestionService(provider=resolve_ingestion_provider(mode))
    result = service.run_once(batch_size=batch_size, cursor_override=cursor_override, attempt=attempt)
    return asdict(result)
