from __future__ import annotations

from typing import Any

import mysql.connector
import requests

from addressforge.core.config import (
    ADDRESSFORGE_INGESTION_API_ADAPTER,
    ADDRESSFORGE_INGESTION_API_BATCH_SIZE,
    ADDRESSFORGE_INGESTION_API_TIMEOUT,
    ADDRESSFORGE_INGESTION_API_TOKEN,
    ADDRESSFORGE_INGESTION_API_URL,
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
    ADDRESSFORGE_INGESTION_DB_USER,
    ADDRESSFORGE_INGESTION_MODE,
    ADDRESSFORGE_INGESTION_SOURCE_NAME,
)

from .adapters import ApiAdapterContext, _row_to_record, resolve_api_source_adapter
from .models import IngestionPage


class BaseIngestionProvider:
    def __init__(self, source_name: str) -> None:
        self.source_name = source_name

    def fetch_page(self, cursor_value: str | None, batch_size: int) -> IngestionPage:  # pragma: no cover
        raise NotImplementedError


class ApiIngestionProvider(BaseIngestionProvider):
    def __init__(
        self,
        api_url: str = ADDRESSFORGE_INGESTION_API_URL,
        token: str = ADDRESSFORGE_INGESTION_API_TOKEN,
        timeout: int = ADDRESSFORGE_INGESTION_API_TIMEOUT,
        source_name: str = ADDRESSFORGE_INGESTION_SOURCE_NAME,
        adapter_name: str = "legacy_batch_orders",
    ) -> None:
        super().__init__(source_name=source_name)
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.adapter = resolve_api_source_adapter(adapter_name)

    def fetch_page(self, cursor_value: str | None, batch_size: int) -> IngestionPage:
        if not self.api_url:
            raise ValueError("ADDRESSFORGE_INGESTION_API_URL is not configured")
        
        import logging
        logger = logging.getLogger("addressforge")
        logger.info(f"ApiIngestionProvider: Adapter={type(self.adapter).__name__}, URL={self.api_url}")
        
        session = requests.Session()
        try:
            return self.adapter.fetch_page(
                session,
                ApiAdapterContext(
                    base_url=self.api_url,
                    source_name=self.source_name,
                    timeout=self.timeout,
                    token=self.token,
                ),
                cursor_value,
                batch_size or ADDRESSFORGE_INGESTION_API_BATCH_SIZE,
            )
        finally:
            session.close()


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
        self.field_mapping = {
            "external_id": ADDRESSFORGE_INGESTION_DB_EXTERNAL_ID_COLUMN,
            "raw_address_text": ADDRESSFORGE_INGESTION_DB_RAW_ADDRESS_COLUMN,
            "city": ADDRESSFORGE_INGESTION_DB_CITY_COLUMN,
            "province": ADDRESSFORGE_INGESTION_DB_PROVINCE_COLUMN,
            "postal_code": ADDRESSFORGE_INGESTION_DB_POSTAL_CODE_COLUMN,
            "latitude": ADDRESSFORGE_INGESTION_DB_LATITUDE_COLUMN,
            "longitude": ADDRESSFORGE_INGESTION_DB_LONGITUDE_COLUMN,
            "cursor_value": self.cursor_column,
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
            records.append(
                _row_to_record(
                    self.source_name,
                    normalized_row,
                    field_mapping=self.field_mapping,
                    cursor_field=self.cursor_column,
                )
            )
            if row.get(self.cursor_column) is not None:
                next_cursor = str(row.get(self.cursor_column))
        has_more = len(rows) >= batch_limit
        return IngestionPage(records=records, next_cursor=next_cursor, has_more=has_more, source_name=self.source_name)


def resolve_ingestion_provider(mode: str | None = None) -> BaseIngestionProvider:
    normalized_mode = (mode or ADDRESSFORGE_INGESTION_MODE or "api").strip().lower()
    if normalized_mode in {"api", "pull", "remote"}:
        return ApiIngestionProvider()
    if normalized_mode in {"db", "database", "direct"}:
        return DatabaseIngestionProvider()
    raise ValueError(f"Unsupported ingestion mode: {mode}")

