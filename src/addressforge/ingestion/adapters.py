from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from addressforge.core.common import normalize_space
from addressforge.core.config import (
    ADDRESSFORGE_DEFAULT_LOOKBACK_SECONDS,
    ADDRESSFORGE_INGESTION_API_ADAPTER,
    ADDRESSFORGE_INGESTION_API_BATCHLIST_ENDPOINT,
    ADDRESSFORGE_INGESTION_API_BATCHLIST_HIDE_ASSOCIATED,
    ADDRESSFORGE_INGESTION_API_BATCHLIST_HIDE_SUB_REFERRER,
    ADDRESSFORGE_INGESTION_API_BRANCH,
    ADDRESSFORGE_INGESTION_API_CURSOR_FIELD,
    ADDRESSFORGE_INGESTION_API_DATA_PATH,
    ADDRESSFORGE_INGESTION_API_DRIVER_COUNT_ENDPOINT,
    ADDRESSFORGE_INGESTION_API_DRIVER_COUNT_HIDE_ASSOCIATED,
    ADDRESSFORGE_INGESTION_API_DRIVER_COUNT_HIDE_SUB_REFERRER,
    ADDRESSFORGE_INGESTION_API_FIELD_MAPPING_JSON,
    ADDRESSFORGE_INGESTION_API_HAS_MORE_FIELD,
    ADDRESSFORGE_INGESTION_API_METHOD,
    ADDRESSFORGE_INGESTION_API_NEXT_CURSOR_FIELD,
    ADDRESSFORGE_INGESTION_API_ORDERS_ENDPOINT,
    ADDRESSFORGE_INGESTION_API_ORDERS_HIDE_ASSOCIATED,
    ADDRESSFORGE_INGESTION_API_ORDERS_HIDE_SUB_REFERRER,
    ADDRESSFORGE_INGESTION_API_REQUIRE_SUCCESS_STATUS,
    ADDRESSFORGE_INGESTION_API_SUCCESS_STATUS_VALUE,
)

from .models import IngestionPage, IngestionRecord


def _split_path(path: str | None) -> list[str]:
    return [part.strip() for part in str(path or "").split(".") if part.strip()]


def _dig(value: Any, path: str | None, default: Any = None) -> Any:
    current = value
    for part in _split_path(path):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return default
    return current if current is not None else default


def _load_field_mapping(raw_json: str | None) -> dict[str, str]:
    if not raw_json:
        return {}
    try:
        data = json.loads(raw_json)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items() if value is not None}


def _get_row_value(row: dict[str, Any], *candidates: str) -> Any:
    for candidate in candidates:
        if not candidate:
            continue
        if "." in candidate:
            value = _dig(row, candidate, None)
            if value not in (None, ""):
                return value
            continue
        value = row.get(candidate)
        if value not in (None, ""):
            return value
    return None


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_to_record(
    source_name: str,
    row: dict[str, Any],
    *,
    field_mapping: dict[str, str] | None = None,
    cursor_field: str | None = None,
) -> IngestionRecord:
    mapping = field_mapping or {}
    external_id = normalize_space(
        str(
            _get_row_value(
                row,
                mapping.get("external_id"),
                "external_id",
                "order_id",
                "id",
                "record_id",
            )
            or ""
        )
    )
    raw_address_text = normalize_space(
        str(
            _get_row_value(
                row,
                mapping.get("raw_address_text"),
                "raw_address_text",
                "delivery_address",
                "address_text",
                "address",
            )
            or ""
        )
    )
    city = normalize_space(
        str(
            _get_row_value(
                row,
                mapping.get("city"),
                "city",
                "COMM",
                "municipality",
            )
            or ""
        )
    ) or None
    province = normalize_space(
        str(
            _get_row_value(
                row,
                mapping.get("province"),
                "province",
                "PROVINCE",
                "state",
            )
            or ""
        )
    ) or None
    postal_code = normalize_space(
        str(
            _get_row_value(
                row,
                mapping.get("postal_code"),
                "postal_code",
                "postcode",
                "zip",
                "zipcode",
            )
            or ""
        )
    ) or None
    country_code = normalize_space(
        str(
            _get_row_value(
                row,
                mapping.get("country_code"),
                "country_code",
                "country",
            )
            or "CA"
        )
    ) or "CA"
    latitude = _float_or_none(
        _get_row_value(row, mapping.get("latitude"), "latitude", "lat", "gps_lat", "gps.lat")
    )
    longitude = _float_or_none(
        _get_row_value(row, mapping.get("longitude"), "longitude", "lon", "lng", "gps_lon", "gps.lon")
    )
    cursor_value = None
    resolved_cursor_field = mapping.get("cursor_value") or cursor_field
    if resolved_cursor_field:
        cursor_raw = _get_row_value(row, resolved_cursor_field)
        cursor_value = None if cursor_raw in (None, "") else str(cursor_raw)
    return IngestionRecord(
        external_id=external_id,
        raw_address_text=raw_address_text,
        source_name=source_name,
        cursor_value=cursor_value,
        city=city,
        province=province,
        postal_code=postal_code,
        country_code=country_code,
        latitude=latitude,
        longitude=longitude,
        source_payload=dict(row),
    )


@dataclass(frozen=True)
class ApiAdapterContext:
    base_url: str
    source_name: str
    timeout: int
    token: str = ""


class BaseApiSourceAdapter:
    adapter_name = "base"

    def fetch_page(
        self,
        session: requests.Session,
        context: ApiAdapterContext,
        cursor_value: str | None,
        batch_size: int,
    ) -> IngestionPage:  # pragma: no cover
        raise NotImplementedError


class GenericApiSourceAdapter(BaseApiSourceAdapter):
    adapter_name = "generic"

    def __init__(
        self,
        *,
        method: str = ADDRESSFORGE_INGESTION_API_METHOD,
        data_path: str = ADDRESSFORGE_INGESTION_API_DATA_PATH,
        next_cursor_field: str = ADDRESSFORGE_INGESTION_API_NEXT_CURSOR_FIELD,
        has_more_field: str = ADDRESSFORGE_INGESTION_API_HAS_MORE_FIELD,
        require_success_status: bool = ADDRESSFORGE_INGESTION_API_REQUIRE_SUCCESS_STATUS,
        success_status_value: str = ADDRESSFORGE_INGESTION_API_SUCCESS_STATUS_VALUE,
        field_mapping_json: str = ADDRESSFORGE_INGESTION_API_FIELD_MAPPING_JSON,
    ) -> None:
        self.method = method.strip().upper() or "POST"
        self.data_path = data_path
        self.next_cursor_field = next_cursor_field
        self.has_more_field = has_more_field
        self.require_success_status = require_success_status
        self.success_status_value = success_status_value
        self.field_mapping = _load_field_mapping(field_mapping_json)

    def fetch_page(
        self,
        session: requests.Session,
        context: ApiAdapterContext,
        cursor_value: str | None,
        batch_size: int,
    ) -> IngestionPage:
        payload = {
            "cursor": cursor_value,
            "batch_size": batch_size,
            "source_name": context.source_name,
        }
        headers = {"Accept": "application/json"}
        if context.token:
            headers["Authorization"] = f"Bearer {context.token}"
        if self.method == "GET":
            response = session.get(context.base_url, params=payload, headers=headers, timeout=context.timeout)
        else:
            response = session.post(context.base_url, json=payload, headers=headers, timeout=context.timeout)
        response.raise_for_status()
        body = response.json()
        if isinstance(body, list):
            records_payload = body
            next_cursor = None
            has_more = False
        else:
            if self.require_success_status:
                status_value = _dig(body, "status", None)
                if status_value not in (self.success_status_value, None):
                    raise ValueError(f"Generic API adapter returned unexpected status: {status_value}")
            records_payload = _dig(body, self.data_path, None) if self.data_path else None
            if records_payload in (None, ""):
                records_payload = body.get("records") or body.get("data") or []
            next_cursor = _dig(body, self.next_cursor_field, None)
            if next_cursor in (None, ""):
                next_cursor = body.get("next_cursor") or body.get("cursor")
            has_more = _dig(body, self.has_more_field, None)
            if has_more in (None, ""):
                has_more = body.get("has_more") or body.get("more") or False
            has_more = bool(has_more)
        records = [
            _row_to_record(context.source_name, dict(item), field_mapping=self.field_mapping, cursor_field=ADDRESSFORGE_INGESTION_API_CURSOR_FIELD)
            for item in records_payload
            if isinstance(item, dict)
        ]
        return IngestionPage(records=records, next_cursor=None if next_cursor is None else str(next_cursor), has_more=has_more, source_name=context.source_name)


class LegacyBatchOrdersApiAdapter(BaseApiSourceAdapter):
    adapter_name = "legacy_batch_orders"

    def __init__(
        self,
        *,
        branch: int = ADDRESSFORGE_INGESTION_API_BRANCH,
        batchlist_endpoint: str = ADDRESSFORGE_INGESTION_API_BATCHLIST_ENDPOINT,
        driver_count_endpoint: str = ADDRESSFORGE_INGESTION_API_DRIVER_COUNT_ENDPOINT,
        orders_endpoint: str = ADDRESSFORGE_INGESTION_API_ORDERS_ENDPOINT,
        field_mapping_json: str = ADDRESSFORGE_INGESTION_API_FIELD_MAPPING_JSON,
    ) -> None:
        self.branch = branch
        self.batchlist_endpoint = batchlist_endpoint
        self.driver_count_endpoint = driver_count_endpoint
        self.orders_endpoint = orders_endpoint
        self.field_mapping = _load_field_mapping(field_mapping_json)

    def _headers(self, context: ApiAdapterContext) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        # Preserve legacy behavior if the caller configured an empty token:
        # some old company deployments depended on sending an empty Bearer header.
        headers["Authorization"] = f"Bearer {context.token}"
        return headers

    def _request_json(
        self,
        session: requests.Session,
        context: ApiAdapterContext,
        endpoint: str,
        *,
        params: dict[str, Any],
    ) -> Any:
        url = f"{context.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        import logging
        logging.getLogger("addressforge").info(f"Requesting URL: {url} with params: {params}")
        response = session.get(url, params=params, headers=self._headers(context), timeout=context.timeout)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            return []
        status = body.get("status")
        if status not in (ADDRESSFORGE_INGESTION_API_SUCCESS_STATUS_VALUE, None):
            raise ValueError(f"Legacy API adapter returned unexpected status for {endpoint}: {status}")
        return body.get("data") or []

    def _start_time(self, cursor_value: str | None) -> int:
        if cursor_value not in (None, ""):
            try:
                return int(float(str(cursor_value)))
            except (TypeError, ValueError):
                pass
        now_ts = int(datetime.now(tz=timezone.utc).timestamp())
        return max(now_ts - ADDRESSFORGE_DEFAULT_LOOKBACK_SECONDS, 0)

    def fetch_page(
        self,
        session: requests.Session,
        context: ApiAdapterContext,
        cursor_value: str | None,
        batch_size: int,
    ) -> IngestionPage:
        start_time = self._start_time(cursor_value)
        batch_payload = self._request_json(
            session,
            context,
            self.batchlist_endpoint,
            params={
                "branch": self.branch,
                "hide_associated": ADDRESSFORGE_INGESTION_API_BATCHLIST_HIDE_ASSOCIATED,
                "hide_sub_referrer": ADDRESSFORGE_INGESTION_API_BATCHLIST_HIDE_SUB_REFERRER,
                "start_time": start_time,
            },
        )
        batch_ids = [
            str(batch.get("referer"))
            for batch in batch_payload
            if isinstance(batch, dict)
            and str(batch.get("referer") or "").startswith("HA")
            and int(batch.get("refer_count") or 0) > 0
        ]

        records: list[IngestionRecord] = []
        next_cursor = start_time
        for batch_id in batch_ids:
            drivers_payload = self._request_json(
                session,
                context,
                self.driver_count_endpoint,
                params={
                    "branch": self.branch,
                    "batch_list": batch_id,
                    "hide_associated": ADDRESSFORGE_INGESTION_API_DRIVER_COUNT_HIDE_ASSOCIATED,
                    "hide_sub_referrer": ADDRESSFORGE_INGESTION_API_DRIVER_COUNT_HIDE_SUB_REFERRER,
                },
            )
            driver_ids = [
                str(driver.get("driver_id"))
                for driver in drivers_payload
                if isinstance(driver, dict) and int(driver.get("order_count") or 0) > 0 and driver.get("driver_id") is not None
            ]
            for driver_id in driver_ids:
                orders_payload = self._request_json(
                    session,
                    context,
                    self.orders_endpoint,
                    params={
                        "driver_id": driver_id,
                        "batch_list": batch_id,
                        "hide_associated": ADDRESSFORGE_INGESTION_API_ORDERS_HIDE_ASSOCIATED,
                        "hide_sub_referrer": ADDRESSFORGE_INGESTION_API_ORDERS_HIDE_SUB_REFERRER,
                        "branch": self.branch,
                    },
                )
                if isinstance(orders_payload, dict):
                    order_rows = orders_payload.get("orders") or []
                else:
                    order_rows = []
                for order in order_rows:
                    if not isinstance(order, dict):
                        continue
                    shipping_status = order.get("shipping_status")
                    if shipping_status not in (0, "0", None):
                        continue
                    add_time = order.get("add_time")
                    if add_time is not None:
                        try:
                            next_cursor = max(next_cursor, int(float(add_time)))
                        except (TypeError, ValueError):
                            pass
                    normalized_order = dict(order)
                    normalized_order.setdefault("external_id", order.get("order_id"))
                    normalized_order.setdefault("raw_address_text", order.get("address"))
                    normalized_order.setdefault("postal_code", order.get("zipcode"))
                    normalized_order.setdefault("latitude", order.get("lat"))
                    normalized_order.setdefault("longitude", order.get("lng"))
                    normalized_order["batch_id"] = batch_id
                    normalized_order["driver_id"] = driver_id
                    records.append(
                        _row_to_record(
                            context.source_name,
                            normalized_order,
                            field_mapping=self.field_mapping,
                            cursor_field="add_time",
                        )
                    )
                    if len(records) >= batch_size:
                        return IngestionPage(
                            records=records,
                            next_cursor=str(next_cursor),
                            has_more=True,
                            source_name=context.source_name,
                        )
        return IngestionPage(
            records=records,
            next_cursor=str(next_cursor),
            has_more=False,
            source_name=context.source_name,
        )


def resolve_api_source_adapter(name: str | None = None) -> BaseApiSourceAdapter:
    normalized = (name or ADDRESSFORGE_INGESTION_API_ADAPTER or "generic").strip().lower()
    if normalized in {"generic", "default"}:
        return GenericApiSourceAdapter()
    if normalized in {"legacy_batch_orders", "legacy", "batch_orders"}:
        return LegacyBatchOrdersApiAdapter()
    raise ValueError(f"Unsupported ingestion API adapter: {name}")
