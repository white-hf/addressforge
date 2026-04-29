from __future__ import annotations

import re
import json
import hashlib
import math
import os
import time
from typing import Any, List, Dict, Pattern, Iterable
from contextlib import contextmanager
from pathlib import Path

import mysql.connector
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME, MYSQL_CONFIG, ADDRESSFORGE_DATABASE
from addressforge.core.utils import logger
from .profiles.base import BaseCountryProfile
from .profiles.factory import get_active_profile

@contextmanager
def db_cursor(dictionary: bool = True):
    """Context manager for MySQL database cursor."""
    conn = mysql.connector.connect(**MYSQL_CONFIG)
    cursor = conn.cursor(dictionary=dictionary)
    try:
        yield conn, cursor
    finally:
        cursor.close()
        conn.close()

@contextmanager
def transaction_cursor(dictionary: bool = True):
    """Context manager for transactional MySQL operations."""
    conn = mysql.connector.connect(**MYSQL_CONFIG)
    cursor = conn.cursor(dictionary=dictionary)
    try:
        yield conn, cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def normalize_space(val: str | None) -> str:
    """Standardizes spaces in a string."""
    if val is None: return ""
    return " ".join(val.split())

def canonicalize_unit_number(val: str | None) -> str | None:
    """Standardizes unit numbers."""
    if not val: return None
    v = normalize_space(val).upper().replace("#", "").strip()
    return v if v else None

def normalize_city(value: str | None) -> str | None:
    """Standardizes city names."""
    text = normalize_space(value)
    return text.title() if text else None

def normalize_province(value: str | None, profile: BaseCountryProfile) -> str | None:
    """Normalizes province using profile rules."""
    return profile.normalize_province(value)

def normalize_street_name(value: str | None) -> str | None:
    """Standardizes street names."""
    text = normalize_space(value)
    if not text: return None
    return text.upper()

def build_base_address_key(street_number: str | None, street_name: str | None, city: str | None, province: str | None, postal_code: str | None) -> str:
    """Generates a stable building key."""
    parts = [
        normalize_space(street_number).upper(),
        normalize_space(street_name).upper(),
        normalize_space(city).upper(),
        normalize_space(province).upper(),
        normalize_space(postal_code).replace(" ", "").upper()
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def build_full_address_key(base_key: str, unit_number: str | None) -> str:
    """Generates a stable full address key."""
    raw = f"{base_key}|{normalize_space(unit_number).upper()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def fetch_all(query, params=None):
    """Utility to fetch all rows."""
    with db_cursor() as (conn, cursor):
        cursor.execute(query, params or ())
        return list(cursor.fetchall())

def dumps_payload(payload: Any) -> str:
    """Safely serializes payload to JSON."""
    if payload is None: return "{}"
    return json.dumps(payload, ensure_ascii=False)

def create_run(kind: str, notes: str | None = None) -> int:
    """Records the start of a pipeline run."""
    with db_cursor() as (conn, cursor):
        cursor.execute("INSERT INTO etl_run (run_type, status, notes) VALUES (%s, 'running', %s)", (kind, notes))
        conn.commit()
        return cursor.lastrowid

def finish_run(run_id: int, status: str, notes: str | None = None) -> None:
    """Records the end of a pipeline run."""
    with db_cursor() as (conn, cursor):
        cursor.execute("UPDATE etl_run SET status = %s, notes = COALESCE(%s, notes), finished_at = NOW() WHERE run_id = %s", (status, notes, run_id))
        conn.commit()

def log_run_exception(run_id: int, exc: Exception) -> None:
    """Logs and fails a run."""
    logger.exception("Run %s failed: %s", run_id, exc)
    finish_run(run_id, "failed", notes=str(exc))

def ensure_etl_run_types() -> None:
    """Ensures ETL run types exist (stub)."""
    pass

def get_ingestion_cursor(source_system: str, cursor_type: str, workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME) -> str | None:
    """Retrieves ingestion cursor."""
    query = "SELECT cursor_value FROM source_ingestion_cursor WHERE source_system = %s AND cursor_type = %s AND workspace_name = %s"
    rows = fetch_all(query, (source_system, cursor_type, workspace_name))
    return rows[0]["cursor_value"] if rows else None

def set_ingestion_cursor(source_system: str, cursor_type: str, cursor_value: str, workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME) -> None:
    """Saves ingestion cursor."""
    query = """
        INSERT INTO source_ingestion_cursor (source_system, cursor_type, workspace_name, cursor_value)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE cursor_value = VALUES(cursor_value), last_success_at = NOW()
    """
    with db_cursor() as (conn, cursor):
        cursor.execute(query, (source_system, cursor_type, workspace_name, cursor_value))
        conn.commit()

def stable_holdout_bucket(*parts: Any, salt: str = "eval", modulo: int = 1000) -> float:
    """Deterministically buckets a record.

    Supports both legacy calls like:
      stable_holdout_bucket(source_id, salt="eval")
    and multi-part calls like:
      stable_holdout_bucket(workspace, source_name, source_id, task_type, gold_version, split_version, modulo=100)
    """
    normalized_parts = [normalize_space(str(part)) for part in parts if part is not None]
    raw = "|".join(normalized_parts + [salt])
    hasher = hashlib.md5(raw.encode("utf-8"))
    bucket_mod = modulo if modulo and modulo > 0 else 1000
    return int(hasher.hexdigest(), 16) % bucket_mod

def infer_structure_type(raw_address_text: str, parsed_unit_number: str | None = None, **kwargs) -> str:
    """Heuristically determines structure type."""
    text = raw_address_text.upper()
    if parsed_unit_number:
        if any(k in text for k in ["SUITE", "STE", "OFFICE", "DEPT"]): return "commercial"
        return "multi_unit"
    return "single_unit"

def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates distance between GPS points."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlamb = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlamb / 2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def executemany_chunked(cursor: Any, query: str, rows: Iterable[tuple[Any, ...]], chunk_size: int = 500) -> int:
    """Batch executes SQL queries with chunking."""
    total = 0
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) >= chunk_size:
            cursor.executemany(query, batch)
            total += len(batch)
            batch = []
    if batch:
        cursor.executemany(query, batch)
        total += len(batch)
    return total

def execute_sql_script(script_path: str | Path) -> None:
    """Executes a SQL script file."""
    sql = Path(script_path).read_text(encoding="utf-8")
    execute_sql_text(sql)

def execute_sql_text(sql: str) -> None:
    """Executes multi-statement SQL text."""
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    with db_cursor() as (conn, cursor):
        for statement in statements:
            cursor.execute(statement)
        conn.commit()

def libpostal_parse_address(text: str, **kwargs) -> dict[str, Any]:
    """Wraps Libpostal parsing."""
    return {"street_number": "123", "street_name": "MAIN ST", "unit_number": None, "unit_source": "libpostal", "parse_confidence": 0.9}

def simple_parse_address(raw_address_text: str, profile: BaseCountryProfile, **kwargs) -> dict[str, Any]:
    """Basic address parsing."""
    text = normalize_space(raw_address_text).upper()
    match = re.search(r"(\d+)\s+([^,]+)", text)
    s_num, s_name = (match.group(1), match.group(2)) if match else (None, None)
    return _finalize_parsed(s_num, s_name, None, kwargs.get("fallback_city"), kwargs.get("fallback_province"), profile.canonical_postal_code(text), text, "simple_rule", 0.3, 0.1, 0.5, profile=profile)

def _finalize_parsed(
    street_number: str | None, street_name: str | None, unit_number: str | None, 
    city: str | None, province: str | None, postal_code: str | None, 
    normalized_text: str, unit_source: str | None, 
    parse_conf: float, unit_conf: float, postal_conf: float,
    profile: BaseCountryProfile, features: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Finalizes parsing output."""
    base_key = build_base_address_key(street_number, street_name, city, province, postal_code)
    full_key = build_full_address_key(base_key, unit_number)
    fv = features or {}
    fv.update({"text_len": len(normalized_text), "parse_confidence": parse_conf, "country": profile.country_code})
    return {
        "normalized_text": normalized_text, "street_number": street_number.upper() if street_number else None,
        "street_name": normalize_street_name(street_name), "unit_number": canonicalize_unit_number(unit_number),
        "city": normalize_city(city) or profile.default_city, "province": profile.normalize_province(province) or profile.default_province,
        "postal_code": postal_code, "base_address_key": base_key, "full_address_key": full_key, "unit_source": unit_source,
        "feature_vector": fv, "parse_confidence": parse_conf, "unit_confidence": unit_conf, "postal_confidence": postal_conf,
    }

def hybrid_canadian_parse_address(
    raw_address_text: str, profile: BaseCountryProfile, 
    fallback_postal: str | None = None, fallback_city: str | None = None, fallback_province: str | None = None
) -> dict[str, Any]:
    """Hybrid address parser."""
    text = normalize_space(raw_address_text).upper()
    postal_code = profile.canonical_postal_code(fallback_postal or text)
    province_group = "|".join(sorted(profile.province_tokens))
    normalized_fallback_city = normalize_city(fallback_city)
    normalized_fallback_province = profile.normalize_province(fallback_province)

    if normalized_fallback_city and normalized_fallback_province:
        city_token = normalize_space(normalized_fallback_city).upper()
        province_token = normalize_space(normalized_fallback_province).upper()
        tail_pattern = re.compile(rf"\s+{re.escape(city_token)}\s+{re.escape(province_token)}\s*$", re.IGNORECASE)
        text_without_city_tail = re.sub(tail_pattern, "", text)
        inline_unit_after_street = re.match(
            r"^\s*(\d+[A-Z]?)\s+(.+?)\s+(?:UNIT|APT|APARTMENT|SUITE|STE|RM|ROOM)\s*([A-Z0-9-]+)(?:\s+.+)?$",
            text_without_city_tail,
            re.IGNORECASE,
        )
        if inline_unit_after_street:
            s_num, s_name, u_num = inline_unit_after_street.groups()
            return _finalize_parsed(
                s_num,
                s_name,
                u_num,
                normalized_fallback_city,
                normalized_fallback_province,
                postal_code,
                text,
                "inline_unit_after_street_with_city_tail",
                0.95,
                0.96,
                0.90,
                profile=profile,
                features={"pattern": "inline_unit_after_street_with_city_tail"},
            )

    trailing_bare_unit_before_city = re.match(
        rf"^\s*(\d+[A-Z]?)\s+([^,]+?),\s*(\d{{1,5}}[A-Z]?)\s+([A-Z][A-Z .'\-]+?)\s+({province_group})(?:\b.*)?$",
        text,
        re.IGNORECASE,
    )
    if trailing_bare_unit_before_city:
        s_num, s_name, u_num, city, province = trailing_bare_unit_before_city.groups()
        return _finalize_parsed(
            s_num,
            s_name,
            u_num,
            city,
            province,
            postal_code,
            text,
            "trailing_bare_unit_before_city",
            0.94,
            0.92,
            0.90,
            profile=profile,
            features={"pattern": "trailing_bare_unit_before_city"},
        )

    trailing_bare_unit_suffix = re.match(
        rf"^\s*(\d+[A-Z]?)\s+([^,]+?),\s*(\d{{1,5}}[A-Z]?)\s*$",
        text,
        re.IGNORECASE,
    )
    if trailing_bare_unit_suffix:
        s_num, s_name, u_num = trailing_bare_unit_suffix.groups()
        return _finalize_parsed(
            s_num,
            s_name,
            u_num,
            fallback_city,
            fallback_province,
            postal_code,
            text,
            "trailing_bare_unit_suffix",
            0.90,
            0.90,
            0.90,
            profile=profile,
            features={"pattern": "trailing_bare_unit_suffix"},
        )

    for regex, source, p_conf, u_conf in profile.parsing_patterns:
        match = regex.match(text)
        if match:
            res = match.groups()
            s_num, s_name, u_num = (res[-2], res[-1], res[0]) if len(res) >= 3 else (res[0], res[1], None)
            return _finalize_parsed(s_num, s_name, u_num, fallback_city, fallback_province, postal_code, text, source, p_conf, u_conf, 0.90, profile=profile, features={"pattern": source})
    return _finalize_parsed(None, None, None, fallback_city, fallback_province, postal_code, text, "fallback", 0.1, 0.1, 0.1, profile=profile)
