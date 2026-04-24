from __future__ import annotations

from typing import Any

import mysql.connector
import requests

from addressforge.core.config import (
    ADDRESSFORGE_INGESTION_API_BATCH_SIZE,
    ADDRESSFORGE_INGESTION_API_TIMEOUT,
    ADDRESSFORGE_INGESTION_API_TOKEN,
    ADDRESSFORGE_INGESTION_API_URL,
    ADDRESSFORGE_INGESTION_DB_BATCH_SIZE,
    ADDRESSFORGE_INGESTION_DB_CITY_COLUMN,
    ADDRESSFORGE_INGESTION_DB_CURSOR_COLUMN,
    ADDRESSFORGE_INGESTION_DB_EXTERNAL_ID_COLUMN,
    ADDRESSFORGE_INGESTION_DB_HOST,
    ADDRESSFORGE_INGESTION_DB_LONGITUDE_COLUMN,
    ADDRESSFORGE_INGESTION_DB_NAME,
    ADDRESSFORGE_INGESTION_DB_PASSWORD,
    ADDRESSFORGE_INGESTION_DB_POSTAL_CODE_COLUMN,
    ADDRESSFORGE_INGESTION_DB_PROVINCE_COLUMN,
    ADDRESSFORGE_INGESTION_DB_RAW_ADDRESS_COLUMN,
    ADDRESSFORGE_INGESTION_DB_TABLE,
    ADDRESSFORGE_INGESTION_DB_USER,
    ADDRESSFORGE_INGESTION_MODE,
    ADDRESSFORGE_INGESTION_SOURCE_NAME,
)
from addressforge.core.common import normalize_space

from .models import IngestionPage, IngestionRecord


class BaseIngestionProvider:
    def __init__(self, source_name: str) -> None:
        self.source_name = source_name

    def fetch_page(self, cursor_value: str | None, batch_size: int) -> IngestionPage:  # pragma: no cover
        raise NotImplementedError


def _record_from_mapping(source_name: str, row: dict[str, Any], cursor_field: str | None = None) -> IngestionRecord:
    external_id = normalize_space(str(row.get("external_id") or row.get("id") or row.get("record_id") or ""))
    raw_address_text = normalize_space(
        str(row.get("raw_address_text") or row.get("address_text") or row.get("address") or "")
    )
    source_payload = dict(row)
    cursor_value = None
    if cursor_field:
        value = row.get(cursor_field)
        cursor_value = None if value is None else str(value)
    latitude = row.get("latitude") or row.get("lat") or row.get("gps_lat")
    longitude = row.get("longitude") or row.get("lon") or row.get("gps_lon")
    try:
        latitude_value = float(latitude) if latitude not in (None, "") else None
    except (TypeError, ValueError):
        latitude_value = None
    try:
        longitude_value = float(longitude) if longitude not in (None, "") else None
    except (TypeError, ValueError):
        longitude_value = None
    return IngestionRecord(
        external_id=external_id,
        raw_address_text=raw_address_text,
        source_name=source_name,
        cursor_value=cursor_value,
        city=normalize_space(str(row.get("city") or row.get("COMM") or row.get("municipality") or "")) or None,
        province=normalize_space(str(row.get("province") or row.get("PROVINCE") or row.get("state") or "")) or None,
        postal_code=normalize_space(str(row.get("postal_code") or row.get("postcode") or row.get("zip") or "")) or None,
        country_code=normalize_space(str(row.get("country_code") or row.get("country") or "CA")) or "CA",
        latitude=latitude_value,
        longitude=longitude_value,
        source_payload=source_payload,
    )


class ApiIngestionProvider(BaseIngestionProvider):
    def __init__(
        self,
        api_url: str = ADDRESSFORGE_INGESTION_API_URL,
        token: str = ADDRESSFORGE_INGESTION_API_TOKEN,
        timeout: int = ADDRESSFORGE_INGESTION_API_TIMEOUT,
        source_name: str = ADDRESSFORGE_INGESTION_SOURCE_NAME,
    ) -> None:
        super().__init__(source_name=source_name)
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def fetch_page(self, cursor_value: str | None, batch_size: int) -> IngestionPage:
        if not self.api_url:
            raise ValueError("ADDRESSFORGE_INGESTION_API_URL is not configured")
        payload = {
            "cursor": cursor_value,
            "batch_size": batch_size or ADDRESSFORGE_INGESTION_API_BATCH_SIZE,
            "source_name": self.source_name,
        }
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        response = requests.post(self.api_url, json=payload, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        body = response.json()
        if isinstance(body, list):
            records_payload = body
            next_cursor = None
            has_more = False
        else:
            records_payload = body.get("records") or body.get("data") or []
            next_cursor = body.get("next_cursor") or body.get("cursor")
            has_more = bool(body.get("has_more") or body.get("more"))
        records = [_record_from_mapping(self.source_name, dict(item)) for item in records_payload]
        return IngestionPage(records=records, next_cursor=next_cursor, has_more=has_more, source_name=self.source_name)


class DatabaseIngestionProvider(BaseIngestionProvider):
    def __init__(
        self,
        host: str = ADDRESSFORGE_INGESTION_DB_HOST,
        user: str = ADDRESSFORGE_INGESTION_DB_USER,
        password: str = ADDRESSFORGE_INGESTION_DB_PASSWORD,
        database: str = ADDRESSFORGE_INGESTION_DB_NAME,
        table: str = ADDRESSFORGE_INGESTION_DB_TABLE,
        cursor_column: str = ADDRESSFORGE_INGESTION_DB_CURSOR_COLUMN,
        source_name: str = ADDRESSFORGE_INGESTION_SOURCE_NAME,
    ) -> None:
        super().__init__(source_name=source_name)
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.table = table
        self.cursor_column = cursor_column
        self._source_column_names = {
            "external_id": ADDRESSFORGE_INGESTION_DB_EXTERNAL_ID_COLUMN,
            "raw_address_text": ADDRESSFORGE_INGESTION_DB_RAW_ADDRESS_COLUMN,
            "city": ADDRESSFORGE_INGESTION_DB_CITY_COLUMN,
            "province": ADDRESSFORGE_INGESTION_DB_PROVINCE_COLUMN,
            "postal_code": ADDRESSFORGE_INGESTION_DB_POSTAL_CODE_COLUMN,
            "latitude": "latitude",
            "longitude": ADDRESSFORGE_INGESTION_DB_LONGITUDE_COLUMN,
        }

    def _connect(self):
        return mysql.connector.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
            raise_on_warnings=True,
        )

    def fetch_page(self, cursor_value: str | None, batch_size: int) -> IngestionPage:
        batch_limit = batch_size or ADDRESSFORGE_INGESTION_DB_BATCH_SIZE
        sql = f"""
            SELECT *
            FROM {self.table}
            {f"WHERE {self.cursor_column} > %s" if cursor_value else ""}
            ORDER BY {self.cursor_column} ASC
            LIMIT %s
        """
        params: tuple[Any, ...] = (cursor_value, batch_limit) if cursor_value else (batch_limit,)
        conn = self._connect()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
        records = []
        next_cursor = None
        for row in rows:
            normalized_row = dict(row)
            records.append(_record_from_mapping(self.source_name, normalized_row, cursor_field=self.cursor_column))
            next_cursor = str(row.get(self.cursor_column)) if row.get(self.cursor_column) is not None else next_cursor
        has_more = len(rows) >= batch_limit
        return IngestionPage(records=records, next_cursor=next_cursor, has_more=has_more, source_name=self.source_name)


def resolve_ingestion_provider(mode: str | None = None) -> BaseIngestionProvider:
    normalized_mode = (mode or ADDRESSFORGE_INGESTION_MODE or "api").strip().lower()
    if normalized_mode in {"api", "pull", "remote"}:
        return ApiIngestionProvider()
    if normalized_mode in {"db", "database", "direct"}:
        return DatabaseIngestionProvider()
    raise ValueError(f"Unsupported ingestion mode: {mode}")
