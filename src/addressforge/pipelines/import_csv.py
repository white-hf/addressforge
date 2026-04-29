from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

from addressforge.core.common import db_cursor, dumps_payload, executemany_chunked, create_run, finish_run
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.core.utils import logger


RAW_INGEST_TABLE = "raw_address_record"


def _normalize_row(row: dict[str, Any], source_name: str, workspace_name: str) -> tuple[Any, ...] | None:
    external_id = str(row.get("external_id") or row.get("id") or "").strip()
    raw_address_text = str(row.get("raw_address_text") or row.get("address_text") or row.get("address") or "").strip()
    if not external_id or not raw_address_text:
        return None
    return (
        workspace_name,
        source_name,
        external_id,
        raw_address_text,
        (row.get("city") or row.get("municipality") or row.get("COMM") or None),
        (row.get("province") or row.get("state") or row.get("PROVINCE") or None),
        (row.get("postal_code") or row.get("postcode") or row.get("zip") or None),
        str(row.get("country_code") or row.get("country") or "CA"),
        row.get("latitude") or row.get("lat") or row.get("gps_lat") or None,
        row.get("longitude") or row.get("lon") or row.get("gps_lon") or None,
        row.get("source_cursor") or row.get("updated_at") or row.get("created_at") or None,
        dumps_payload(row),
    )


def import_csv(csv_path: str, source_name: str | None = None, batch_size: int = 1000) -> dict[str, Any]:
    path = Path(csv_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    resolved_source = source_name or os.getenv("ADDRESSFORGE_INGESTION_SOURCE_NAME", "local_csv")
    workspace_name = os.getenv("ADDRESSFORGE_WORKSPACE_NAME", ADDRESSFORGE_WORKSPACE_NAME)
    run_id = create_run("ingestion", notes=f"csv_import path={path} batch_size={batch_size}")
    rows_seen = 0
    rows_ingested = 0
    payload: list[tuple[Any, ...]] = []
    query = f"""
        INSERT INTO {RAW_INGEST_TABLE} (
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
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows_seen += 1
            normalized = _normalize_row(row, resolved_source, workspace_name)
            if normalized is None:
                continue
            payload.append(normalized)
            if len(payload) >= batch_size:
                with db_cursor() as (conn, cursor):
                    executemany_chunked(cursor, query, payload, chunk_size=batch_size)
                    conn.commit()
                rows_ingested += len(payload)
                payload.clear()
    if payload:
        with db_cursor() as (conn, cursor):
            executemany_chunked(cursor, query, payload, chunk_size=batch_size)
            conn.commit()
        rows_ingested += len(payload)
    finish_run(
        run_id,
        "completed",
        notes=dumps_payload(
            {
                "csv_path": str(path),
                "source_name": resolved_source,
                "rows_seen": rows_seen,
                "rows_ingested": rows_ingested,
            }
        ),
    )
    logger.info(
        "CSV import completed: run_id=%s source=%s rows_seen=%s rows_ingested=%s",
        run_id,
        resolved_source,
        rows_seen,
        rows_ingested,
    )
    return {
        "run_id": run_id,
        "csv_path": str(path),
        "source_name": resolved_source,
        "rows_seen": rows_seen,
        "rows_ingested": rows_ingested,
    }


def main() -> None:
    csv_path = os.getenv("ADDRESSFORGE_IMPORT_CSV_PATH")
    if not csv_path:
        raise SystemExit("ADDRESSFORGE_IMPORT_CSV_PATH is required")
    source_name = os.getenv("ADDRESSFORGE_IMPORT_SOURCE_NAME")
    result = import_csv(csv_path, source_name=source_name)
    print(result)


if __name__ == "__main__":
    main()
