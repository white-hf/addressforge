from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IngestionRecord:
    external_id: str
    raw_address_text: str
    source_name: str
    cursor_value: str | None = None
    city: str | None = None
    province: str | None = None
    postal_code: str | None = None
    country_code: str = "CA"
    latitude: float | None = None
    longitude: float | None = None
    source_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IngestionPage:
    records: list[IngestionRecord]
    next_cursor: str | None
    has_more: bool
    source_name: str


@dataclass(frozen=True)
class IngestionResult:
    run_id: int
    source_name: str
    records_seen: int
    records_ingested: int
    next_cursor: str | None
    has_more: bool
    mode: str
