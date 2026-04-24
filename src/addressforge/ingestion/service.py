from __future__ import annotations

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
    ) -> None:
        self.provider = provider or resolve_ingestion_provider()
        self.target_table = target_table
        self.source_name = source_name
        self.cursor_type = cursor_type

    def _upsert_records(self, records: list[IngestionRecord]) -> int:
        if not records:
            return 0
        query = f"""
            INSERT INTO {self.target_table} (
                source_name, external_id, raw_address_text, city, province, postal_code,
                country_code, latitude, longitude, source_cursor, source_payload, is_active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE
                raw_address_text = VALUES(raw_address_text),
                city = VALUES(city),
                province = VALUES(province),
                postal_code = VALUES(postal_code),
                country_code = VALUES(country_code),
                latitude = VALUES(latitude),
                longitude = VALUES(longitude),
                source_cursor = VALUES(source_cursor),
                source_payload = VALUES(source_payload),
                is_active = 1,
                updated_at = CURRENT_TIMESTAMP
        """
        payload: list[tuple[Any, ...]] = []
        for record in records:
            if not record.external_id or not record.raw_address_text:
                continue
            payload.append(
                (
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

    def run_once(self, batch_size: int = 1000) -> IngestionResult:
        run_id = create_run("ingestion", notes=f"{self.source_name} batch_size={batch_size}")
        try:
            current_cursor = get_ingestion_cursor(self.source_name, self.cursor_type)
            page: IngestionPage = self.provider.fetch_page(current_cursor, batch_size)
            ingested = self._upsert_records(page.records)
            if page.next_cursor:
                set_ingestion_cursor(self.source_name, self.cursor_type, str(page.next_cursor))
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
            finish_run(run_id, "failed", notes=dumps_payload({"error": str(exc)}))
            raise


def run_default_ingestion(batch_size: int = 1000, mode: str | None = None) -> dict[str, Any]:
    service = IngestionService(provider=resolve_ingestion_provider(mode))
    result = service.run_once(batch_size=batch_size)
    return asdict(result)
