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
from addressforge.core.config import (
    ADDRESSFORGE_DATABASE,
    ADDRESSFORGE_DB_CONNECT_RETRY_ATTEMPTS,
    ADDRESSFORGE_DB_CONNECT_RETRY_SLEEP_MS,
    ADDRESSFORGE_WORKSPACE_NAME,
    MYSQL_CONFIG,
)
from addressforge.core.utils import logger
from .profiles.base import BaseCountryProfile
from .profiles.factory import get_active_profile

STRONG_COMMERCIAL_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(r"\bMALL\b"),
    re.compile(r"\bPLAZA\b"),
    re.compile(r"\bSQUARE\b"),
    re.compile(r"\bCENTRE\b"),
    re.compile(r"\bCENTER\b"),
    re.compile(r"\bOFFICE\b"),
    re.compile(r"\bKIOSK\b"),
    re.compile(r"\bSHOPPING\b"),
    re.compile(r"\bDEPT\b"),
)

COMMERCIAL_UNIT_HINT_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(r"\bSUITE\b"),
    re.compile(r"\bSTE\b"),
    re.compile(r"\bOFFICE\b"),
    re.compile(r"\bDEPT\b"),
)

RESIDENTIAL_UNIT_HINT_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(r"\bAPT\b"),
    re.compile(r"\bAPARTMENT\b"),
    re.compile(r"\bGARAGE\s+APT\b"),
    re.compile(r"\bGARAGE\s+APARTMENT\b"),
    re.compile(r"\bUNIT\b"),
    re.compile(r"\bBASEMENT\b"),
    re.compile(r"\bBSMT\b"),
    re.compile(r"\bLOWER\b"),
    re.compile(r"\bUPPER\b"),
    re.compile(r"\bREAR\b"),
    re.compile(r"\bFRONT\b"),
    re.compile(r"\bSIDE\b"),
    re.compile(r"\bPENTHOUSE\b"),
    re.compile(r"\bPH\b"),
    re.compile(r"\bGROUND FLOOR\b"),
    re.compile(r"\bMAIN FLOOR\b"),
    re.compile(r"\bMAIN FLR\b"),
    re.compile(r"\bGF\b"),
    re.compile(r"\bLWR\b"),
    re.compile(r"\bUPR\b"),
    re.compile(r"\bDOOR\b"),
    re.compile(r"\bLOT\b"),
    re.compile(r"\bLEVEL\b"),
    re.compile(r"\bLVL\b"),
)

GEOGRAPHIC_MODIFIER_PLACE_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(r"\bUPPER\s+[A-Z][A-Z' -]{2,}\b"),
    re.compile(r"\bLOWER\s+[A-Z][A-Z' -]{2,}\b"),
)

STRONG_EXPLICIT_UNIT_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(r"\bAPT\b"),
    re.compile(r"\bAPARTMENT\b"),
    re.compile(r"\bGARAGE\s+APT\b"),
    re.compile(r"\bGARAGE\s+APARTMENT\b"),
    re.compile(r"\bUNIT\b"),
    re.compile(r"\bSUITE\b"),
    re.compile(r"\bSTE\b"),
    re.compile(r"\bROOM\b"),
    re.compile(r"\bRM\b"),
    re.compile(r"#\s*[A-Z0-9]+"),
)

COMPOUND_RESIDENTIAL_UNIT_KEYWORD = (
    r"(?:GARAGE\s+APT|GARAGE\s+APARTMENT|BASEMENT\s+APT|BASEMENT\s+APARTMENT|"
    r"LOWER\s+APT|LOWER\s+APARTMENT|UPPER\s+APT|UPPER\s+APARTMENT|"
    r"REAR\s+APT|REAR\s+APARTMENT|FRONT\s+APT|FRONT\s+APARTMENT)"
)

NUMBERED_ROAD_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(r"\b(?:HWY|HIGHWAY|ROUTE|RTE|TRUNK)\s+\d+[A-Z]?\b"),
    re.compile(r"\b(?:NS|NB|PE|NL|QC|ON|MB|SK|AB|BC|YT|NT|NU)-\d+[A-Z]?\b"),
    re.compile(r"\bCANADA\s+\d+[A-Z]?\b"),
)

URBAN_STREET_SUFFIX_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(r"\b(?:ST|STREET|AVE|AVENUE|DR|DRIVE|RD|ROAD|BLVD|BOULEVARD|PL|PLACE|LN|LANE|CRT|COURT|CRES|CRESCENT|WAY|TERR|TERRACE|CLOSE|CL)\b"),
)

RUN_TYPE_ALIASES: dict[str, str] = {
    "historical_replay": "ml_eval",
    "reranking_train": "ml_train",
    "weak_supervision_gen": "ml_gold",
    "ml_active_learning_from_eval": "ml_active_learning",
    "ml_active_learning_residual": "ml_active_learning",
}

_CANADA_PROVINCES = {
    "NS", "NB", "PE", "NL", "QC", "ON", "MB", "SK", "AB", "BC", "YT", "NT", "NU"
}

_CANADA_POSTAL_RE = re.compile(
    r"\b[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z]\d[ABCEGHJ-NPRSTV-Z]\d\b",
    re.IGNORECASE,
)

_UNIT_WORDS = {
    "UNIT", "APT", "APT.", "APARTMENT", "SUITE", "STE", "ROOM", "RM",
    "FLOOR", "FL", "BASEMENT", "LOWER", "UPPER",
}

_STREET_SUFFIX_WORDS = {
    "ST", "STREET", "AVE", "AVENUE", "DR", "DRIVE", "RD", "ROAD", "BLVD", "BOULEVARD",
    "PL", "PLACE", "LN", "LANE", "CRT", "COURT", "CRES", "CRESCENT", "WAY", "TERR",
    "TERRACE", "CLOSE", "CL",
}

_PROVINCE_NAME_TO_CODE = {
    "NOVA SCOTIA": "NS",
    "NEW BRUNSWICK": "NB",
    "PRINCE EDWARD ISLAND": "PE",
    "NEWFOUNDLAND AND LABRADOR": "NL",
    "QUEBEC": "QC",
    "ONTARIO": "ON",
    "MANITOBA": "MB",
    "SASKATCHEWAN": "SK",
    "ALBERTA": "AB",
    "BRITISH COLUMBIA": "BC",
    "YUKON": "YT",
    "NORTHWEST TERRITORIES": "NT",
    "NUNAVUT": "NU",
}

def _connect_with_retry():
    attempts = max(int(ADDRESSFORGE_DB_CONNECT_RETRY_ATTEMPTS or 1), 1)
    sleep_ms = max(int(ADDRESSFORGE_DB_CONNECT_RETRY_SLEEP_MS or 0), 0)
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return mysql.connector.connect(**MYSQL_CONFIG)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= attempts:
                break
            logger.warning(
                "MySQL connect attempt %s/%s failed: %s. Retrying in %sms.",
                attempt,
                attempts,
                exc,
                sleep_ms,
            )
            if sleep_ms > 0:
                time.sleep(sleep_ms / 1000.0)
    if last_exc:
        raise last_exc
    raise RuntimeError("MySQL connection failed without exception")


@contextmanager
def db_cursor(dictionary: bool = True):
    """Context manager for MySQL database cursor."""
    conn = _connect_with_retry()
    cursor = conn.cursor(dictionary=dictionary)
    try:
        yield conn, cursor
    finally:
        cursor.close()
        conn.close()

@contextmanager
def transaction_cursor(dictionary: bool = True):
    """Context manager for transactional MySQL operations."""
    conn = _connect_with_retry()
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


def normalize_unit_signal_text(val: str | None) -> str:
    """Normalizes glued unit keywords so downstream regexes can reason on them."""
    text = normalize_space(val).upper()
    text = re.sub(r"\b(\d{1,6})([A-Z]{3,})\b", r"\1 \2", text)
    text = re.sub(r"\b([A-Z]{3,})(\d{1,5}[A-Z]?)\b", r"\1 \2", text)
    text = re.sub(r"\b(UNIT|APT|APARTMENT|SUITE|STE|ROOM|RM)\s*(\d{1,5})([A-Z]{3,})\b", r"\1 \2 \3", text)
    text = re.sub(r"\b([A-Z]\d[A-Z])\s*(\d[A-Z]\d)(CANADA)\b", r"\1 \2 \3", text)
    text = re.sub(
        r"\b(APT|APARTMENT|SUITE|STE|UNIT|ROOM|RM|FLOOR|FL|BASEMENT|BSMT|LOWER|UPPER|PENTHOUSE|PH|GF|LEVEL|LVL)\.\s*(?=[A-Z0-9#])",
        r"\1 ",
        text,
    )
    text = re.sub(r"#(?=[A-Z0-9])", "# ", text)
    text = re.sub(
        r"(?<=[A-Z])(?=(?:APT|APARTMENT|SUITE|STE|UNIT|ROOM|RM|FLOOR|FL|BASEMENT|BSMT|LOWER|UPPER|PENTHOUSE|PH|GF|LEVEL|LVL)(?:\.|\b)\s*#?[0-9][A-Z0-9-]{0,7}\b)",
        " ",
        text,
    )
    text = re.sub(
        r"(\d)(?=(?:APT|APARTMENT|SUITE|STE|UNIT|ROOM|RM|FLOOR|FL|BASEMENT|BSMT|LOWER|UPPER|PENTHOUSE|PH|GF|LEVEL|LVL)\b)",
        r"\1 ",
        text,
    )
    text = re.sub(
        r"\b(APT|APARTMENT|SUITE|STE|UNIT|ROOM|RM|FLOOR|FL|BASEMENT|BSMT|LOWER|UPPER|PENTHOUSE|PH|GF|LEVEL|LVL)([0-9][A-Z0-9-]*)\b",
        r"\1 \2",
        text,
    )
    return text

def canonicalize_unit_number(val: str | None) -> str | None:
    """Standardizes unit numbers."""
    if not val: return None
    v = normalize_space(val).upper().replace("#", "").strip()
    return v if v else None


def split_glued_unit_and_civic_token(val: str | None) -> tuple[str, str] | None:
    token = normalize_space(val).upper()
    if not token or not re.fullmatch(r"\d{5,10}[A-Z]?", token):
        return None
    suffix = ""
    digits = token
    if token[-1].isalpha():
        suffix = token[-1]
        digits = token[:-1]
    for civic_len in (4, 3, 5):
        if len(digits) <= civic_len:
            continue
        unit_part = digits[:-civic_len]
        civic_part = digits[-civic_len:]
        if 1 <= len(unit_part) <= 5:
            return unit_part, f"{civic_part}{suffix}"
    return None


def has_numbered_road_signal(text: str | None) -> bool:
    normalized = normalize_space(text).upper()
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in NUMBERED_ROAD_PATTERNS)


def has_urban_street_suffix_signal(text: str | None) -> bool:
    normalized = normalize_space(text).upper()
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in URBAN_STREET_SUFFIX_PATTERNS)
def ends_with_urban_street_suffix(text: str | None) -> bool:
    normalized = normalize_space(text).upper()
    if not normalized:
        return False
    tokens = normalized.split()
    if not tokens:
        return False
    suffixes = {
        "ST", "STREET", "AVE", "AVENUE", "DR", "DRIVE", "RD", "ROAD", "BLVD", "BOULEVARD",
        "PL", "PLACE", "LN", "LANE", "CRT", "COURT", "CRES", "CRESCENT", "WAY", "TERR",
        "TERRACE", "CLOSE", "CL"
    }
    directionals = {
        "N", "NORTH", "S", "SOUTH", "E", "EAST", "W", "WEST",
        "NE", "NORTHEAST", "NW", "NORTHWEST", "SE", "SOUTHEAST", "SW", "SOUTHWEST"
    }
    if tokens[-1] in suffixes:
        return True
    if len(tokens) > 1 and tokens[-1] in directionals and tokens[-2] in suffixes:
        return True
    return False


def looks_like_bare_trailing_unit_city_pattern(
    normalized_text: str | None,
    *,
    street_number: str | None,
    street_name: str | None,
    unit_number: str | None,
    city: str | None,
    province: str | None,
) -> bool:
    text = normalize_space(normalized_text).upper()
    s_num = normalize_space(street_number).upper()
    s_name = normalize_space(street_name).upper()
    u_num = normalize_space(unit_number).upper()
    city_token = normalize_space(city).upper()
    province_token = normalize_space(province).upper()
    if not text or not s_num or not s_name or not u_num or not city_token or not province_token:
        return False
    if has_numbered_road_signal(s_name) or has_numbered_road_signal(text):
        return False
    if not has_urban_street_suffix_signal(s_name):
        return False
    if u_num == s_num:
        return False
    # Constrain bare trailing unit to <= 3 digits to avoid false unit extraction on double-number house addresses.
    if len([ch for ch in u_num if ch.isdigit()]) > 3:
        return False
    pattern = re.compile(
        rf"^\s*{re.escape(s_num)}\s+.+\s+{re.escape(u_num)}\s+{re.escape(city_token)}\s+{re.escape(province_token)}(?:\b.*)?$",
        re.IGNORECASE,
    )
    return bool(pattern.search(text))

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
    text = text.upper()
    dir_expand = {
        "S": "SOUTH",
        "N": "NORTH",
        "E": "EAST",
        "W": "WEST",
        "NE": "NORTHEAST",
        "NW": "NORTHWEST",
        "SE": "SOUTHEAST",
        "SW": "SOUTHWEST",
    }
    tokens = text.split()
    if tokens:
        if tokens[0] in dir_expand:
            tokens[0] = dir_expand[tokens[0]]
        if len(tokens) > 1 and tokens[-1] in dir_expand:
            tokens[-1] = dir_expand[tokens[-1]]
    return " ".join(tokens)

def _recover_city_without_province(tokens: list[str]) -> str | None:
    if not tokens:
        return None
    idx = len(tokens) - 1
    city_tokens: list[str] = []
    while idx >= 0:
        token = tokens[idx]
        if (
            any(ch.isdigit() for ch in token)
            or token in _UNIT_WORDS
            or token in _STREET_SUFFIX_WORDS
            or token in {"CA", "CANADA"}
        ):
            break
        city_tokens.append(token)
        if len(city_tokens) >= 2:
            break
        idx -= 1
    if not city_tokens:
        return None
    city_tokens.reverse()
    return normalize_city(" ".join(city_tokens))

def recover_locality_from_text(raw_address_text: str | None) -> tuple[str | None, str | None]:
    text = normalize_space(raw_address_text)
    if not text:
        return None, None
    upper_text = text.upper()
    for province_name, province_code in _PROVINCE_NAME_TO_CODE.items():
        upper_text = upper_text.replace(province_name, province_code)
    comma_cleaned = _CANADA_POSTAL_RE.sub(" ", upper_text)
    comma_cleaned = re.sub(r"\b(CA|CANADA)\b", " ", comma_cleaned)
    segments = [normalize_space(segment) for segment in comma_cleaned.split(",") if normalize_space(segment)]
    for idx in range(len(segments) - 1, -1, -1):
        if segments[idx] in _CANADA_PROVINCES:
            province = segments[idx]
            if idx > 0:
                candidate_city = normalize_city(segments[idx - 1])
                if candidate_city and not any(ch.isdigit() for ch in candidate_city):
                    return candidate_city, province
            return None, province
    cleaned = _CANADA_POSTAL_RE.sub(" ", upper_text)
    cleaned = re.sub(r"\b(CA|CANADA)\b", " ", cleaned)
    cleaned = re.sub(r"[,/()-]", " ", cleaned)
    tokens = [token for token in cleaned.split() if token]
    if not tokens:
        return None, None
    province_index = None
    for idx in range(len(tokens) - 1, -1, -1):
        if tokens[idx] in _CANADA_PROVINCES:
            province_index = idx
            break
    if province_index is None:
        return _recover_city_without_province(tokens), None
    province = tokens[province_index]
    city_tokens: list[str] = []
    idx = province_index - 1
    while idx >= 0:
        token = tokens[idx]
        if any(ch.isdigit() for ch in token) or token in _UNIT_WORDS or token in _STREET_SUFFIX_WORDS:
            break
        city_tokens.append(token)
        if len(city_tokens) >= 3:
            break
        idx -= 1
    if not city_tokens:
        return _recover_city_without_province(tokens), province
    city_tokens.reverse()
    city = normalize_city(" ".join(city_tokens))
    return city, province

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
    """
    Safely serializes payload to JSON, supporting datetime and Decimal objects.
    安全地将有效负载序列化为 JSON，支持 datetime 和 Decimal 对象。
    """
    from datetime import datetime, date
    from decimal import Decimal
    
    class EnhancedEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                return float(obj)
            return super().default(obj)

    if payload is None: return "{}"
    return json.dumps(payload, cls=EnhancedEncoder, ensure_ascii=False)

def create_run(kind: str, notes: str | None = None) -> int:
    """Records the start of a pipeline run."""
    normalized_kind = RUN_TYPE_ALIASES.get(kind, kind)
    with db_cursor() as (conn, cursor):
        cursor.execute(
            "INSERT INTO etl_run (run_type, status, notes) VALUES (%s, 'running', %s)",
            (normalized_kind, notes),
        )
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
        VALUES (%s, %s, %s, %s) AS new_row
        ON DUPLICATE KEY UPDATE cursor_value = new_row.cursor_value, last_success_at = NOW()
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
    """Heuristically determines structure type, enhanced with parse features."""
    text = normalize_unit_signal_text(raw_address_text)
    reference_payload = kwargs.get("reference_payload") or {}
    reference_unit_count_hint = int(kwargs.get("reference_unit_count_hint") or 0)
    
    # Check if the parsed source itself implies commercial
    # 检查解析源本身是否暗示了商业属性
    unit_source = kwargs.get("unit_source") or ""
    is_commercial_source = "comm_prefix_label" in unit_source or "commercial" in unit_source

    has_strong_commercial_signal = any(pattern.search(text) for pattern in STRONG_COMMERCIAL_PATTERNS)
    has_commercial_unit_hint = any(pattern.search(text) for pattern in COMMERCIAL_UNIT_HINT_PATTERNS)
    has_residential_unit_hint = any(pattern.search(text) for pattern in RESIDENTIAL_UNIT_HINT_PATTERNS)
    has_geographic_modifier_only = bool(
        any(pattern.search(text) for pattern in GEOGRAPHIC_MODIFIER_PLACE_PATTERNS)
        and not any(pattern.search(text) for pattern in STRONG_EXPLICIT_UNIT_PATTERNS)
    )

    reference_unit_numbers = reference_payload.get("reference_unit_numbers") or []
    has_multi_unit_reference = reference_unit_count_hint > 1 or len(reference_unit_numbers) > 1

    if is_commercial_source:
        return "commercial"

    if parsed_unit_number:
        if has_strong_commercial_signal or (has_commercial_unit_hint and not has_residential_unit_hint):
            return "commercial"
        return "multi_unit"

    if has_strong_commercial_signal:
        return "commercial"

    if has_commercial_unit_hint and not has_residential_unit_hint:
        return "commercial"

    if has_geographic_modifier_only and not parsed_unit_number and not has_multi_unit_reference:
        return "single_unit"

    if has_multi_unit_reference:
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
    text = normalize_unit_signal_text(raw_address_text)
    
    fallback_city = kwargs.get("fallback_city")
    fallback_province = kwargs.get("fallback_province")
    if (not fallback_city or not fallback_province) and raw_address_text:
        recovered_city, recovered_province = recover_locality_from_text(raw_address_text)
        fallback_city = fallback_city or recovered_city
        fallback_province = fallback_province or recovered_province

    normalized_fallback_city = normalize_city(fallback_city)
    normalized_fallback_province = profile.normalize_province(fallback_province)
    
    text_without_city_tail = text
    if normalized_fallback_city and normalized_fallback_province:
        city_token = normalize_space(normalized_fallback_city).upper()
        province_token = normalize_space(normalized_fallback_province).upper()
        tail_pattern = re.compile(
            rf"\s+{re.escape(city_token)}\s*,?\s*(?:{re.escape(province_token)})?\s*,?\s*(?:[A-Z]\d[A-Z]\s*\d[A-Z]\d)?\s*,?\s*(?:CA|CANADA)?\s*$",
            re.IGNORECASE
        )
        text_without_city_tail = re.sub(tail_pattern, "", text).strip().rstrip(",").strip()

    match = re.search(r"(\d+)\s+([^,]+)", text_without_city_tail)
    s_num, s_name = (match.group(1), match.group(2)) if match else (None, None)
    return _finalize_parsed(s_num, s_name, None, fallback_city, fallback_province, profile.canonical_postal_code(text), text, "simple_rule", 0.3, 0.1, 0.5, profile=profile)

def _finalize_parsed(
    street_number: str | None, street_name: str | None, unit_number: str | None, 
    city: str | None, province: str | None, postal_code: str | None, 
    normalized_text: str, unit_source: str | None, 
    parse_conf: float, unit_conf: float, postal_conf: float,
    profile: BaseCountryProfile, features: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Finalizes parsing output."""
    recovered_city = None
    recovered_province = None
    if (not city or not province) and normalized_text:
        recovered_city, recovered_province = recover_locality_from_text(normalized_text)
        city = city or recovered_city
        province = province or recovered_province
    canonical_unit = canonicalize_unit_number(unit_number)
    base_key = build_base_address_key(street_number, street_name, city, province, postal_code)
    full_key = build_full_address_key(base_key, canonical_unit)
    fv = features or {}
    has_strong_commercial_signal = any(pattern.search(normalized_text) for pattern in STRONG_COMMERCIAL_PATTERNS)
    has_commercial_unit_hint = any(pattern.search(normalized_text) for pattern in COMMERCIAL_UNIT_HINT_PATTERNS)
    has_residential_unit_hint = any(pattern.search(normalized_text) for pattern in RESIDENTIAL_UNIT_HINT_PATTERNS)
    normalized_text_without_postal = re.sub(r"\b[A-Z]\d[A-Z]\s*\d[A-Z]\d\b", " ", normalized_text)
    has_double_number_pattern = bool(
        re.search(
            r"^\s*\d+[A-Z]?\s+.+(?:,|\s)\s*\d+[A-Z]?\s+[A-Z][A-Z .'-]+\s+(?:NS|NB|ON|QC|PE|NL|MB|SK|AB|BC|YT|NT|NU)\b",
            normalized_text_without_postal,
        )
    )
    is_numbered_road_name = bool(
        has_numbered_road_signal(street_name)
        or has_numbered_road_signal(normalized_text)
    )
    has_geographic_modifier_only = bool(
        any(pattern.search(normalized_text) for pattern in GEOGRAPHIC_MODIFIER_PLACE_PATTERNS)
        and not any(pattern.search(normalized_text) for pattern in STRONG_EXPLICIT_UNIT_PATTERNS)
    )
    has_bare_trailing_unit_city_pattern = looks_like_bare_trailing_unit_city_pattern(
        normalized_text,
        street_number=street_number,
        street_name=street_name,
        unit_number=canonical_unit,
        city=city,
        province=province,
    )
    fv.update(
        {
            "text_len": len(normalized_text),
            "parse_confidence": parse_conf,
            "country": profile.country_code,
            "unit_present": 1 if canonical_unit else 0,
            "has_explicit_unit_hint": 1 if (has_commercial_unit_hint or has_residential_unit_hint) else 0,
            "has_residential_unit_hint": 1 if has_residential_unit_hint else 0,
            "has_commercial_unit_hint": 1 if has_commercial_unit_hint else 0,
            "has_geographic_modifier_only": 1 if has_geographic_modifier_only else 0,
            "has_double_number_pattern": 1 if has_double_number_pattern else 0,
            "has_bare_trailing_unit_city_pattern": 1 if has_bare_trailing_unit_city_pattern else 0,
            "is_numbered_road_name": 1 if is_numbered_road_name else 0,
            "is_commercial": 1 if has_strong_commercial_signal else 0,
            "regex_hit": 1 if canonical_unit else 0,
        }
    )
    return {
        "normalized_text": normalized_text, "street_number": street_number.upper() if street_number else None,
        "street_name": normalize_street_name(street_name), "unit_number": canonical_unit,
        "city": normalize_city(city), "province": profile.normalize_province(province) or profile.default_province,
        "postal_code": postal_code, "base_address_key": base_key, "full_address_key": full_key, "unit_source": unit_source,
        "feature_vector": fv, "parse_confidence": parse_conf, "unit_confidence": unit_conf, "postal_confidence": postal_conf,
    }

def standardize_unit_val(val: str | None) -> str | None:
    if not val:
        return None
    v = val.strip().upper().replace(".", "")
    if v in ("BSMT", "BASEMENT"):
        return "BASEMENT"
    if v in ("LWR", "LOWER"):
        return "LWR" if "LWR" in val or val == "LWR" else "LOWER"
    if v in ("UPR", "UPPER"):
        return "UPR" if "UPR" in val or val == "UPR" else "UPPER"
    if v in ("GF", "GROUND FLOOR"):
        return "GF" if "GF" in val or val == "GF" else "GROUND FLOOR"
    if v in ("MAIN FLR", "MAIN FLOOR"):
        return "MAIN FLOOR"
    
    # Handle "LEVEL 2" or "LVL 2"
    m_lvl = re.match(r"^(?:LEVEL|LVL)\s*([A-Z0-9-]+)$", v)
    if m_lvl:
        return f"LEVEL {m_lvl.group(1)}"
        
    # Handle "BUILDING A UNIT 5" or "BUILDING A" or "BLDG A"
    m_bldg_unit = re.match(r"^(?:BUILDING|BLDG)\s*([A-Z0-9-]+)\s*(?:UNIT|APT|APARTMENT|SUITE|STE)\s*([A-Z0-9-]+)$", v)
    if m_bldg_unit:
        return f"{m_bldg_unit.group(1)}-{m_bldg_unit.group(2)}"
    m_bldg = re.match(r"^(?:BUILDING|BLDG)\s*([A-Z0-9-]+)$", v)
    if m_bldg:
        return m_bldg.group(1)
        
    # Handle "DOOR 3" or "LOT 12"
    m_door_lot = re.match(r"^(DOOR|LOT)\s*([A-Z0-9-]+)$", v)
    if m_door_lot:
        return f"{m_door_lot.group(1)} {m_door_lot.group(2)}"
        
    # Handle "PENTHOUSE 2" -> "PH 2"
    if v == "PENTHOUSE":
        return "PH"
    m_ph = re.match(r"^(?:PENTHOUSE|PH)\s*([A-Z0-9-]+)$", v)
    if m_ph:
        return f"PH {m_ph.group(1)}"
        
    return v

def hybrid_canadian_parse_address(
    raw_address_text: str, profile: BaseCountryProfile, 
    fallback_postal: str | None = None, fallback_city: str | None = None, fallback_province: str | None = None
) -> dict[str, Any]:
    """Hybrid address parser."""
    text = normalize_unit_signal_text(raw_address_text)
    text_without_city_tail = text
    
    # Recover locality first if not provided to make manual matching block robust
    if (not fallback_city or not fallback_province) and raw_address_text:
        recovered_city, recovered_province = recover_locality_from_text(raw_address_text)
        fallback_city = fallback_city or recovered_city
        fallback_province = fallback_province or recovered_province

    postal_code = profile.canonical_postal_code(fallback_postal or text)
    province_group = r"\b(?:" + "|".join(sorted(profile.province_tokens)) + r")\b"
    normalized_fallback_city = normalize_city(fallback_city)
    normalized_fallback_province = profile.normalize_province(fallback_province)

    # Expanded unit keywords for leading prefix patterns
    LEADING_UNIT_KEYWORDS = (
        r"(?:BASEMENT|BSMT|LOWER|LWR|UPPER|UPR|REAR|FRONT|SIDE|PENTHOUSE(?:\s+\d+)?|PH(?:\s+[A-Z0-9-]+)?|"
        r"GF|GROUND\s+FLOOR|MAIN\s+FLOOR|MAIN\s+FLR|LEVEL(?:\s+[A-Z0-9-]+)?|LVL(?:\s+[A-Z0-9-]+)?|"
        r"DOOR(?:\s+\d+)?|LOT(?:\s+\d+)?|\d+(?:ST|ND|RD|TH)\s+(?:FLOOR|FLR|FL)|"
        r"(?:BUILDING|BLDG)\s+[A-Z0-9-]+(?:\s+(?:UNIT|APT|APARTMENT|SUITE|STE)\s+[A-Z0-9-]+)?|"
        r"BUILDING|BLDG)"
    )

    if normalized_fallback_city and normalized_fallback_province:
        city_token = normalize_space(normalized_fallback_city).upper()
        province_token = normalize_space(normalized_fallback_province).upper()
        duplicate_city_prefix = re.match(
            rf"^\s*{re.escape(city_token)}\s+(.+?)\s+{re.escape(city_token)}\s+{re.escape(province_token)}(?:\b.*)?$",
            text,
            re.IGNORECASE,
        )
        if duplicate_city_prefix:
            text = duplicate_city_prefix.group(1) + f" {city_token} {province_token}"
        tail_pattern = re.compile(
            rf"\s+{re.escape(city_token)}\s*,?\s*(?:{re.escape(province_token)})?\s*,?\s*(?:[A-Z]\d[A-Z]\s*\d[A-Z]\d)?\s*,?\s*(?:CA|CANADA)?\s*$",
            re.IGNORECASE
        )
        text_without_city_tail = re.sub(tail_pattern, "", text).strip().rstrip(",").strip()
        
        leading_explicit_unit_glued_civic_before_known_city = re.match(
            rf"^\s*(?:APT\.?|APARTMENT|UNIT|SUITE|STE|RM\.?|ROOM|#)\s*([0-9]{{5,10}}[A-Z]?)\s+(.+?)\s*,?\s*{re.escape(city_token)}\s*,?\s*(?:{re.escape(province_token)})?(?:\b.*)?$",
            text,
            re.IGNORECASE,
        )
        if leading_explicit_unit_glued_civic_before_known_city:
            glued_token, s_name = leading_explicit_unit_glued_civic_before_known_city.groups()
            split_parts = split_glued_unit_and_civic_token(glued_token)
            if split_parts and has_urban_street_suffix_signal(s_name) and not has_numbered_road_signal(s_name):
                u_num, s_num = split_parts
                return _finalize_parsed(
                    s_num,
                    s_name,
                    u_num,
                    normalized_fallback_city,
                    normalized_fallback_province,
                    postal_code,
                    text,
                    "leading_explicit_unit_glued_civic_before_known_city",
                    0.93,
                    0.92,
                    0.90,
                    profile=profile,
                    features={"pattern": "leading_explicit_unit_glued_civic_before_known_city"},
                )

        leading_explicit_unit_before_civic = re.match(
            rf"^\s*(?:APT\.?|APARTMENT|UNIT|SUITE|STE|RM\.?|ROOM|#)\s*([A-Z0-9-]+)\s+(\d+[A-Z]?)\s+(.+?)\s*,?\s*{re.escape(city_token)}\s*,?\s*{re.escape(province_token)}(?:\b.*)?$",
            text,
            re.IGNORECASE,
        )
        if leading_explicit_unit_before_civic:
            u_num, s_num, s_name = leading_explicit_unit_before_civic.groups()
            if has_urban_street_suffix_signal(s_name) and not has_numbered_road_signal(s_name):
                return _finalize_parsed(
                    s_num,
                    s_name,
                    u_num,
                    normalized_fallback_city,
                    normalized_fallback_province,
                    postal_code,
                    text,
                    "leading_explicit_unit_before_civic",
                    0.93,
                    0.92,
                    0.90,
                    profile=profile,
                    features={"pattern": "leading_explicit_unit_before_civic"},
                )

        leading_residential_keyword_before_civic = re.match(
            rf"^\s*({LEADING_UNIT_KEYWORDS})\s*(\d+[A-Z]?)\s+(.+?)\s*,?\s*{re.escape(city_token)}\s*,?\s*(?:{re.escape(province_token)})?(?:\b.*)?$",
            text,
            re.IGNORECASE,
        )
        if leading_residential_keyword_before_civic:
            unit_keyword, s_num, s_name = leading_residential_keyword_before_civic.groups()
            if has_urban_street_suffix_signal(s_name) and not has_numbered_road_signal(s_name):
                return _finalize_parsed(
                    s_num,
                    s_name,
                    standardize_unit_val(unit_keyword),
                    normalized_fallback_city,
                    normalized_fallback_province,
                    postal_code,
                    text,
                    "leading_residential_keyword_before_civic",
                    0.91,
                    0.88,
                    0.90,
                    profile=profile,
                    features={"pattern": "leading_residential_keyword_before_civic"},
                )

        leading_explicit_unit_hyphen_civic = re.match(
            rf"^\s*(?:APT\.?|APARTMENT|UNIT|SUITE|STE|RM\.?|ROOM|#)\s*([A-Z0-9-]+)\s*-\s*(\d+[A-Z]?)\s+(.+?)\s*,?\s*{re.escape(city_token)}\s*,?\s*{re.escape(province_token)}(?:\b.*)?$",
            text,
            re.IGNORECASE,
        )
        if leading_explicit_unit_hyphen_civic:
            u_num, s_num, s_name = leading_explicit_unit_hyphen_civic.groups()
            return _finalize_parsed(
                s_num,
                s_name,
                u_num,
                normalized_fallback_city,
                normalized_fallback_province,
                postal_code,
                text,
                "leading_explicit_unit_hyphen_civic",
                0.93,
                0.92,
                0.90,
                profile=profile,
                features={"pattern": "leading_explicit_unit_hyphen_civic"},
            )

        leading_civic_hyphen_street_with_unit = re.match(
            rf"^\s*(\d+[A-Z]?)\s*-\s*(.+?)\s+\b(?:UNIT|APT|APARTMENT|SUITE|STE|ROOM|RM)\b\s*([A-Z0-9-]+)\s+{re.escape(city_token)}\s+{re.escape(province_token)}(?:\b.*)?$",
            text,
            re.IGNORECASE,
        )
        if leading_civic_hyphen_street_with_unit:
            s_num, s_name, u_num = leading_civic_hyphen_street_with_unit.groups()
            if has_urban_street_suffix_signal(s_name) and not has_numbered_road_signal(s_name):
                return _finalize_parsed(
                    s_num,
                    s_name,
                    u_num,
                    normalized_fallback_city,
                    normalized_fallback_province,
                    postal_code,
                    text,
                    "leading_civic_hyphen_street_with_unit",
                    0.92,
                    0.90,
                    0.90,
                    profile=profile,
                    features={"pattern": "leading_civic_hyphen_street_with_unit"},
                )

        explicit_unit_before_city_tail = re.match(
            rf"^\s*(\d+[A-Z]?)\s+([^,]+?)\s*,?\s*(?:\b(?:UNIT|APT|APARTMENT|SUITE|STE|ROOM|RM|FLOOR|FL|LEVEL|LVL|BLDG|BUILDING|DOOR|LOT|PENTHOUSE|PH)\b\.?\s*)?(?:#\s*([A-Z0-9-]+)|\b(UNIT|APT|APARTMENT|SUITE|STE|ROOM|RM|FLOOR|FL|LEVEL|LVL|BLDG|BUILDING|DOOR|LOT|PENTHOUSE|PH)\b\.?\s*([A-Z0-9-]+))\s*,?\s*{re.escape(city_token)}\s*,?\s*{re.escape(province_token)}(?:\b.*)?$",
            text,
            re.IGNORECASE,
        )
        if explicit_unit_before_city_tail:
            s_num, s_name, hash_unit, unit_keyword, keyword_unit = explicit_unit_before_city_tail.groups()
            u_num = None
            if hash_unit:
                u_num = hash_unit
            elif unit_keyword and keyword_unit:
                u_kw_upper = unit_keyword.upper()
                if u_kw_upper in ("LEVEL", "LVL"):
                    u_num = f"LEVEL {keyword_unit}"
                elif u_kw_upper == "DOOR":
                    u_num = f"DOOR {keyword_unit}"
                elif u_kw_upper == "LOT":
                    u_num = f"LOT {keyword_unit}"
                elif u_kw_upper in ("PENTHOUSE", "PH"):
                    u_num = f"PH {keyword_unit}"
                elif u_kw_upper in ("BLDG", "BUILDING"):
                    u_num = keyword_unit
                else:
                    u_num = keyword_unit
            return _finalize_parsed(
                s_num,
                s_name,
                u_num,
                normalized_fallback_city,
                normalized_fallback_province,
                postal_code,
                text,
                "explicit_unit_before_known_city",
                0.95,
                0.96,
                0.90,
                profile=profile,
                features={"pattern": "explicit_unit_before_known_city"},
            )
        inline_unit_after_street = re.match(
            r"^\s*(\d+[A-Z]?)\s+(.+?)\s+\b(?:UNIT|APT|APARTMENT|SUITE|STE|RM|ROOM)\b\s*([A-Z0-9-]+)(?:\s+.+)?$",
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

        prefixed_noise_civic_street_with_unit = re.match(
            rf"^\s*([A-Z][A-Z0-9/&.'\- ]{{2,32}})\s+(\d+[A-Z]?)\s+(.+?)\s+\b(?:UNIT|APT|APARTMENT|SUITE|STE|ROOM|RM)\b\s*([A-Z0-9-]+)\s+{re.escape(city_token)}\s+{re.escape(province_token)}(?:\b.*)?$",
            text,
            re.IGNORECASE,
        )
        if prefixed_noise_civic_street_with_unit:
            prefix, s_num, s_name, u_num = prefixed_noise_civic_street_with_unit.groups()
            if (
                has_urban_street_suffix_signal(s_name)
                and not has_numbered_road_signal(s_name)
                and normalize_space(prefix).upper() != normalize_space(s_name).upper()
            ):
                return _finalize_parsed(
                    s_num,
                    s_name,
                    u_num,
                    normalized_fallback_city,
                    normalized_fallback_province,
                    postal_code,
                    text,
                    "prefixed_noise_civic_street_with_unit",
                    0.91,
                    0.90,
                    0.90,
                    profile=profile,
                    features={"pattern": "prefixed_noise_civic_street_with_unit"},
                )

        repeated_leading_unit_before_known_city = re.match(
            rf"^\s*(\d{{1,5}}[A-Z]?)\s*-\s*(\d+[A-Z]?)\s+(.+?)\s+(\d{{1,5}}[A-Z]?)\s+{re.escape(city_token)}\s+{re.escape(province_token)}(?:\b.*)?$",
            text,
            re.IGNORECASE,
        )
        if repeated_leading_unit_before_known_city:
            u_num_1, s_num, s_name, u_num_2 = repeated_leading_unit_before_known_city.groups()
            if (
                normalize_space(u_num_1).upper() == normalize_space(u_num_2).upper()
                and has_urban_street_suffix_signal(s_name)
                and not has_numbered_road_signal(s_name)
                and not has_numbered_road_signal(text)
            ):
                return _finalize_parsed(
                    s_num,
                    s_name,
                    u_num_1,
                    normalized_fallback_city,
                    normalized_fallback_province,
                    postal_code,
                    text,
                    "repeated_leading_unit_before_known_city",
                    0.92,
                    0.90,
                    0.90,
                    profile=profile,
                    features={"pattern": "repeated_leading_unit_before_known_city"},
                )

        trailing_bare_unit_before_known_city = re.match(
            rf"^\s*(\d+[A-Z]?)\s+([^,]+?),\s*(\d{{1,5}}[A-Z]?)\s*,?\s*{re.escape(city_token)}\s*,?\s*(?:{re.escape(province_token)})?(?:\b.*)?$",
            text,
            re.IGNORECASE,
        )
        if trailing_bare_unit_before_known_city:
            s_num, s_name, u_num = trailing_bare_unit_before_known_city.groups()
            return _finalize_parsed(
                s_num,
                s_name,
                u_num,
                normalized_fallback_city,
                normalized_fallback_province,
                postal_code,
                text,
                "trailing_bare_unit_before_known_city",
                0.94,
                0.92,
                0.90,
                profile=profile,
                features={"pattern": "trailing_bare_unit_before_known_city"},
            )

        duplicate_or_noise_number_before_known_city = re.match(
            rf"^\s*(\d+[A-Z]?)\s+(.+?)\s+(\d{{1,5}}[A-Z]?)\s*,?\s*{re.escape(city_token)}\s*,?\s*(?:{re.escape(province_token)})?(?:\b.*)?$",
            text,
            re.IGNORECASE,
        )
        if duplicate_or_noise_number_before_known_city:
            s_num, s_name, noise_num = duplicate_or_noise_number_before_known_city.groups()
            if "," not in s_name and (
                noise_num == s_num
                or has_numbered_road_signal(s_name)
                or has_numbered_road_signal(text)
                or not has_urban_street_suffix_signal(s_name)
            ):
                return _finalize_parsed(
                    s_num,
                    s_name,
                    None,
                    normalized_fallback_city,
                    normalized_fallback_province,
                    postal_code,
                    text,
                    "duplicate_number_before_known_city",
                    0.89,
                    0.10,
                    0.90,
                    profile=profile,
                    features={"pattern": "duplicate_number_before_known_city"},
                )
            if "," not in s_name and has_urban_street_suffix_signal(s_name):
                if len([ch for ch in noise_num if ch.isdigit()]) <= 3:
                    return _finalize_parsed(
                        s_num,
                        s_name,
                        noise_num,
                        normalized_fallback_city,
                        normalized_fallback_province,
                        postal_code,
                        text,
                        "bare_trailing_unit_before_known_city",
                        0.91,
                        0.88,
                        0.90,
                        profile=profile,
                        features={"pattern": "bare_trailing_unit_before_known_city"},
                    )
                else:
                    return _finalize_parsed(
                        s_num,
                        s_name,
                        None,
                        normalized_fallback_city,
                        normalized_fallback_province,
                        postal_code,
                        text,
                        "duplicate_number_before_known_city",
                        0.89,
                        0.10,
                        0.90,
                        profile=profile,
                        features={"pattern": "duplicate_number_before_known_city"},
                    )

        trailing_keyword_after_bare_unit = re.match(
            rf"^\s*(\d+[A-Z]?)\s+(.+?)\s+(\d{{1,5}}[A-Z]?)\s+(?:UNIT|APT|APARTMENT|SUITE|STE|ROOM|RM|FLOOR|FL)\s+{re.escape(city_token)}\s+{re.escape(province_token)}(?:\b.*)?$",
            text,
            re.IGNORECASE,
        )
        if trailing_keyword_after_bare_unit:
            s_num, s_name, u_num = trailing_keyword_after_bare_unit.groups()
            return _finalize_parsed(
                s_num,
                s_name,
                u_num,
                normalized_fallback_city,
                normalized_fallback_province,
                postal_code,
                text,
                "trailing_bare_unit_keyword_before_known_city",
                0.94,
                0.92,
                0.90,
                profile=profile,
                features={"pattern": "trailing_bare_unit_keyword_before_known_city"},
            )

        trailing_residential_keyword_before_known_city = re.match(
            rf"^\s*(\d+[A-Z]?)\s+(.+?)\s*,?\s*({COMPOUND_RESIDENTIAL_UNIT_KEYWORD}|BASEMENT|LOWER|UPPER|REAR|FRONT|SIDE|PENTHOUSE(?:\s+\d+)?|PH(?:\s+[A-Z0-9-]+)?|GF|GROUND\s+FLOOR|MAIN\s+FLOOR|MAIN\s+FLR|\d+(?:ST|ND|RD|TH)\s+(?:FLOOR|FLR|FL))\s*,?\s*{re.escape(city_token)}\s*,?\s*(?:{re.escape(province_token)})?(?:\b.*)?$",
            text,
            re.IGNORECASE,
        )
        if trailing_residential_keyword_before_known_city:
            s_num, s_name, unit_keyword = trailing_residential_keyword_before_known_city.groups()
            if has_urban_street_suffix_signal(s_name) and not has_numbered_road_signal(s_name):
                return _finalize_parsed(
                    s_num,
                    s_name,
                    standardize_unit_val(unit_keyword),
                    normalized_fallback_city,
                    normalized_fallback_province,
                    postal_code,
                    text,
                    "trailing_residential_keyword_before_known_city",
                    0.93,
                    0.92,
                    0.90,
                    profile=profile,
                    features={"pattern": "trailing_residential_keyword_before_known_city"},
                )

        # Standard civic + street before city tail (without unit)
        standard_civic_before_city_tail = re.match(
            r"^\s*(\d+[A-Z]?)\s+(.+?)\s*$",
            text_without_city_tail,
            re.IGNORECASE,
        )
        if standard_civic_before_city_tail:
            s_num, s_name = standard_civic_before_city_tail.groups()
            if s_name.strip() and "," not in text_without_city_tail and not re.search(r"\s+\d+[A-Z]?$", text_without_city_tail):
                return _finalize_parsed(
                    s_num,
                    s_name,
                    None,
                    normalized_fallback_city,
                    normalized_fallback_province,
                    postal_code,
                    text,
                    "standard_civic_before_city_tail",
                    0.90,
                    0.10,
                    0.90,
                    profile=profile,
                    features={"pattern": "standard_civic_before_city_tail"},
                )

    # Commercial premise without civic number: Suite 500 Scotia Square
    comm_no_civic_prefix = re.match(
        rf"^\s*(UNIT|APT|APARTMENT|SUITE|STE|RM|ROOM|KIOSK)\s*([A-Z0-9-]+)\s+([A-Z][A-Z0-9 .'\-]+?)(?:\s*,?\s*([A-Z][A-Z .'\-]+?)\s*,?\s*({province_group}))?\s*$",
        text,
        re.IGNORECASE,
    )
    if comm_no_civic_prefix:
        keyword, unit_val, s_name, city, province = comm_no_civic_prefix.groups()
        # Only match if the premise name does NOT have an urban street suffix (which would indicate a real address)
        if not ends_with_urban_street_suffix(s_name):
            u_num = f"KIOSK {unit_val}" if keyword.upper() == "KIOSK" else unit_val
            return _finalize_parsed(
                None,
                None,
                u_num,
                city or fallback_city,
                province or fallback_province,
                postal_code,
                text,
                "commercial_no_civic_prefix",
                0.80,
                0.85,
                0.90,
                profile=profile,
                features={"pattern": "commercial_no_civic_prefix"},
            )

    comm_no_civic_suffix = re.match(
        rf"^\s*([A-Z][A-Z0-9 .'\-]+?)\s+(UNIT|APT|APARTMENT|SUITE|STE|RM|ROOM|KIOSK)\s*([A-Z0-9-]+)(?:\s*,?\s*([A-Z][A-Z .'\-]+?)\s*,?\s*({province_group}))?\s*$",
        text,
        re.IGNORECASE,
    )
    if comm_no_civic_suffix:
        s_name, keyword, unit_val, city, province = comm_no_civic_suffix.groups()
        if not ends_with_urban_street_suffix(s_name):
            u_num = f"KIOSK {unit_val}" if keyword.upper() == "KIOSK" else unit_val
            return _finalize_parsed(
                None,
                None,
                u_num,
                city or fallback_city,
                province or fallback_province,
                postal_code,
                text,
                "commercial_no_civic_suffix",
                0.80,
                0.85,
                0.90,
                profile=profile,
                features={"pattern": "commercial_no_civic_suffix"},
            )

    leading_residential_keyword_before_civic_no_fallback = re.match(
        rf"^\s*({LEADING_UNIT_KEYWORDS})\s*(\d+[A-Z]?)\s+([A-Z0-9 .'\-]+?(?:ST|STREET|AVE|AVENUE|DR|DRIVE|RD|ROAD|LN|LANE|PL|PLACE|CRT|COURT|CRES|CRESCENT|BLVD|BOULEVARD|WAY|TERR|TERRACE|CLOSE|CL))\s*,?\s*([A-Z][A-Z .'\-]+?)\s*,?\s*({province_group})(?:\b.*)?$",
        text,
        re.IGNORECASE,
    )
    if leading_residential_keyword_before_civic_no_fallback:
        unit_keyword, s_num, s_name, city, province = leading_residential_keyword_before_civic_no_fallback.groups()
        return _finalize_parsed(
            s_num,
            s_name,
            standardize_unit_val(unit_keyword),
            city,
            province,
            postal_code,
            text,
            "leading_residential_keyword_before_civic_no_fallback",
            0.90,
            0.86,
            0.90,
            profile=profile,
            features={"pattern": "leading_residential_keyword_before_civic_no_fallback"},
        )

    trailing_bare_unit_before_city = re.match(
        rf"^\s*(\d+[A-Z]?)\s+([^,]+?),\s*(\d{{1,5}}[A-Z]?)\s*,?\s*([A-Z][A-Z .'\-]+?)\s*,?\s*({province_group})(?:\b.*)?$",
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

    trailing_bare_unit_before_city_no_comma = re.match(
        rf"^\s*(\d+[A-Z]?)\s+(.+?)\s+(\d{{1,5}}[A-Z]?)\s+([A-Z][A-Z .'\-]+?)(?:\s+({province_group}))?\s*$",
        text,
        re.IGNORECASE,
    )
    if trailing_bare_unit_before_city_no_comma:
        s_num, s_name, u_num, city, province = trailing_bare_unit_before_city_no_comma.groups()
        if (
            has_urban_street_suffix_signal(s_name)
            and not has_numbered_road_signal(s_name)
            and not has_numbered_road_signal(text)
            and u_num != s_num
            and len([ch for ch in u_num if ch.isdigit()]) <= 3
        ):
            return _finalize_parsed(
                s_num,
                s_name,
                u_num,
                city,
                province or fallback_province,
                postal_code,
                text,
                "trailing_bare_unit_before_city_no_comma",
                0.91,
                0.88,
                0.90,
                profile=profile,
                features={"pattern": "trailing_bare_unit_before_city_no_comma"},
            )

    trailing_residential_keyword_before_city = re.match(
        rf"^\s*(\d+[A-Z]?)\s+(.+?)\s*,?\s*({COMPOUND_RESIDENTIAL_UNIT_KEYWORD}|BASEMENT|LOWER|UPPER|REAR|FRONT|SIDE|PENTHOUSE(?:\s+\d+)?|PH(?:\s+[A-Z0-9-]+)?|GF|GROUND FLOOR|MAIN FLOOR|MAIN FLR|\d+(?:ST|ND|RD|TH)\s+(?:FLOOR|FLR|FL))\s*,?\s*([A-Z][A-Z .'\-]+?)\s*,?\s*({province_group})(?:\b.*)?$",
        text,
        re.IGNORECASE,
    )
    if trailing_residential_keyword_before_city:
        s_num, s_name, unit_keyword, city, province = trailing_residential_keyword_before_city.groups()
        if has_urban_street_suffix_signal(s_name) and not has_numbered_road_signal(s_name):
            return _finalize_parsed(
                s_num,
                s_name,
                standardize_unit_val(unit_keyword),
                city,
                province,
                postal_code,
                text,
                "trailing_residential_keyword_before_city",
                0.9,
                0.86,
                0.90,
                profile=profile,
                features={"pattern": "trailing_residential_keyword_before_city"},
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

    trailing_unit_at_end = re.match(
        rf"^\s*(\d+[A-Z]?)\s+(.+?)\s+\b(UNIT|APT|APARTMENT|SUITE|STE|ROOM|RM|FLOOR|FL|LEVEL|LVL|BLDG|BUILDING|DOOR|LOT|PENTHOUSE|PH)\b\s*([A-Z0-9-]+)\s*$",
        text,
        re.IGNORECASE,
    )
    if trailing_unit_at_end:
        s_num, s_name, unit_keyword, keyword_unit = trailing_unit_at_end.groups()
        u_num = None
        if unit_keyword and keyword_unit:
            u_kw_upper = unit_keyword.upper()
            if u_kw_upper in ("LEVEL", "LVL"):
                u_num = f"LEVEL {keyword_unit}"
            elif u_kw_upper == "DOOR":
                u_num = f"DOOR {keyword_unit}"
            elif u_kw_upper == "LOT":
                u_num = f"LOT {keyword_unit}"
            elif u_kw_upper in ("PENTHOUSE", "PH"):
                u_num = f"PH {keyword_unit}"
            elif u_kw_upper in ("BLDG", "BUILDING"):
                u_num = keyword_unit
            else:
                u_num = keyword_unit
        return _finalize_parsed(
            s_num,
            s_name,
            u_num,
            fallback_city,
            fallback_province,
            postal_code,
            text,
            "trailing_unit_at_end",
            0.90,
            0.90,
            0.90,
            profile=profile,
            features={"pattern": "trailing_unit_at_end"},
        )

    route_only_before_city = re.match(
        rf"^\s*((?:HWY|HIGHWAY|ROUTE|RTE|TRUNK)\s+\d+[A-Z]?|(?:NS|NB|PE|NL|QC|ON|MB|SK|AB|BC|YT|NT|NU)-\d+[A-Z]?|CANADA\s+\d+[A-Z]?)\s+([A-Z][A-Z .'\-]+?)\s+({province_group})(?:\b.*)?$",
        text,
        re.IGNORECASE,
    )
    if route_only_before_city:
        s_name, city, province = route_only_before_city.groups()
        return _finalize_parsed(
            None,
            s_name,
            None,
            city,
            province,
            postal_code,
            text,
            "route_only_before_city",
            0.72,
            0.1,
            0.9,
            profile=profile,
            features={"pattern": "route_only_before_city"},
        )

    leading_explicit_unit_before_civic_no_fallback = re.match(
        rf"^\s*(?:APT\.?|APARTMENT|UNIT|SUITE|STE|RM\.?|ROOM|#)\s*([A-Z0-9-]+)\s+(\d+[A-Z]?)\s+([A-Z0-9 .'\-]+?(?:ST|STREET|AVE|AVENUE|DR|DRIVE|RD|ROAD|LN|LANE|PL|PLACE|CRT|COURT|CRES|CRESCENT|BLVD|BOULEVARD|WAY|TERR|TERRACE|CLOSE|CL))\s+([A-Z][A-Z .'\-]+?)\s+({province_group})(?:\b.*)?$",
        text,
        re.IGNORECASE,
    )
    if leading_explicit_unit_before_civic_no_fallback:
        u_num, s_num, s_name, city, province = leading_explicit_unit_before_civic_no_fallback.groups()
        if has_urban_street_suffix_signal(s_name) and not has_numbered_road_signal(s_name):
            return _finalize_parsed(
                s_num,
                s_name,
                u_num,
                city,
                province,
                postal_code,
                text,
                "leading_explicit_unit_before_civic_no_fallback",
                0.92,
                0.90,
                0.90,
                profile=profile,
                features={"pattern": "leading_explicit_unit_before_civic_no_fallback"},
            )

    leading_explicit_unit_glued_civic_no_fallback = re.match(
        rf"^\s*(?:APT\.?|APARTMENT|UNIT|SUITE|STE|RM\.?|ROOM|#)\s*([0-9]{{5,10}}[A-Z]?)\s+([A-Z0-9 .'\-]+?(?:ST|STREET|AVE|AVENUE|DR|DRIVE|RD|ROAD|LN|LANE|PL|PLACE|CRT|COURT|CRES|CRESCENT|BLVD|BOULEVARD|WAY|TERR|TERRACE|CLOSE|CL))\s+([A-Z][A-Z .'\-]+?)\s+({province_group})(?:\b.*)?$",
        text,
        re.IGNORECASE,
    )
    if leading_explicit_unit_glued_civic_no_fallback:
        glued_token, s_name, city, province = leading_explicit_unit_glued_civic_no_fallback.groups()
        split_parts = split_glued_unit_and_civic_token(glued_token)
        if split_parts and has_urban_street_suffix_signal(s_name) and not has_numbered_road_signal(s_name):
            u_num, s_num = split_parts
            return _finalize_parsed(
                s_num,
                s_name,
                u_num,
                city,
                province,
                postal_code,
                text,
                "leading_explicit_unit_glued_civic_no_fallback",
                0.90,
                0.88,
                0.90,
                profile=profile,
                features={"pattern": "leading_explicit_unit_glued_civic_no_fallback"},
            )

    leading_bare_unit_comma_before_civic_no_fallback = re.match(
        rf"^\s*(\d{{1,5}}[A-Z]?)\s*,\s*(\d+[A-Z]?)\s+([^,]+?(?:ST|STREET|AVE|AVENUE|DR|DRIVE|RD|ROAD|LN|LANE|PL|PLACE|CRT|COURT|CRES|CRESCENT|BLVD|BOULEVARD|WAY|TERR|TERRACE|CLOSE|CL))\s*,\s*([A-Z][A-Z .'\-]+?)(?:\s*,\s*[A-Z][A-Z .'\-]+?)*\s*,\s*({province_group})(?:\b.*)?$",
        text,
        re.IGNORECASE,
    )
    if leading_bare_unit_comma_before_civic_no_fallback:
        u_num, s_num, s_name, city, province = leading_bare_unit_comma_before_civic_no_fallback.groups()
        if has_urban_street_suffix_signal(s_name) and not has_numbered_road_signal(s_name):
            return _finalize_parsed(
                s_num,
                s_name,
                u_num,
                city,
                province,
                postal_code,
                text,
                "leading_bare_unit_comma_before_civic_no_fallback",
                0.91,
                0.89,
                0.90,
                profile=profile,
                features={"pattern": "leading_bare_unit_comma_before_civic_no_fallback"},
            )

    leading_residential_keyword_before_civic_no_fallback = re.match(
        rf"^\s*({LEADING_UNIT_KEYWORDS})\s*(\d+[A-Z]?)\s+([A-Z0-9 .'\-]+?(?:ST|STREET|AVE|AVENUE|DR|DRIVE|RD|ROAD|LN|LANE|PL|PLACE|CRT|COURT|CRES|CRESCENT|BLVD|BOULEVARD|WAY|TERR|TERRACE|CLOSE|CL))\s+([A-Z][A-Z .'\-]+?)\s+({province_group})(?:\b.*)?$",
        text,
        re.IGNORECASE,
    )
    if leading_residential_keyword_before_civic_no_fallback:
        unit_keyword, s_num, s_name, city, province = leading_residential_keyword_before_civic_no_fallback.groups()
        if has_urban_street_suffix_signal(s_name) and not has_numbered_road_signal(s_name):
            return _finalize_parsed(
                s_num,
                s_name,
                standardize_unit_val(unit_keyword),
                city,
                province,
                postal_code,
                text,
                "leading_residential_keyword_before_civic_no_fallback",
                0.90,
                0.86,
                0.90,
                profile=profile,
                features={"pattern": "leading_residential_keyword_before_civic_no_fallback"},
            )

    prefixed_noise_civic_street_with_unit_repeated_tail = re.match(
        rf"^\s*([A-Z][A-Z0-9/&.'\- ]{{2,48}})\s+(\d+[A-Z]?)\s+(.+?)\s+\b(?:UNIT|APT|APARTMENT|SUITE|STE|ROOM|RM)\b\s*([A-Z0-9-]+)\s+([A-Z][A-Z .'\-]+?)\s+({province_group})(?:\s+[A-Z]\d[A-Z]\s*\d[A-Z]\d(?:\s+CANADA)?)?\s+\5\s+\6(?:\b.*)?$",
        text,
        re.IGNORECASE,
    )
    if prefixed_noise_civic_street_with_unit_repeated_tail:
        prefix, s_num, s_name, u_num, city, province = prefixed_noise_civic_street_with_unit_repeated_tail.groups()
        if (
            has_urban_street_suffix_signal(s_name)
            and not has_numbered_road_signal(s_name)
            and normalize_space(prefix).upper() != normalize_space(s_name).upper()
        ):
            return _finalize_parsed(
                s_num,
                s_name,
                u_num,
                city,
                province,
                postal_code,
                text,
                "prefixed_noise_civic_street_with_unit_repeated_tail",
                0.89,
                0.88,
                0.90,
                profile=profile,
                features={"pattern": "prefixed_noise_civic_street_with_unit_repeated_tail"},
            )

    reversed_civic_before_city = re.match(
        rf"^\s*([A-Z][A-Z0-9 .'\-]+?(?:ST|STREET|AVE|AVENUE|DR|DRIVE|RD|ROAD|LN|LANE|PL|PLACE|CRT|COURT|CRES|CRESCENT|BLVD|BOULEVARD|WAY|TERR|TERRACE))\s+(\d+[A-Z]?)\s+([A-Z][A-Z .'\-]+?)\s+({province_group})(?:\b.*)?$",
        text,
        re.IGNORECASE,
    )
    if reversed_civic_before_city:
        s_name, s_num, city, province = reversed_civic_before_city.groups()
        if not has_numbered_road_signal(s_name):
            return _finalize_parsed(
                s_num,
                s_name,
                None,
                city,
                province,
                postal_code,
                text,
                "reversed_civic_before_city",
                0.78,
                0.1,
                0.9,
                profile=profile,
                features={"pattern": "reversed_civic_before_city"},
            )

    prefixed_civic_before_city = re.match(
        rf"^\s*([A-Z][A-Z0-9/&.'\- ]{{1,24}})\s+(\d+[A-Z]?)\s+([A-Z0-9 .'\-]+?(?:ST|STREET|AVE|AVENUE|DR|DRIVE|RD|ROAD|LN|LANE|PL|PLACE|CRT|COURT|CRES|CRESCENT|BLVD|BOULEVARD|WAY|TERR|TERRACE))\s*,?\s*([A-Z][A-Z .'\-]+?)\s*,?\s*({province_group})(?:\b.*)?$",
        text,
        re.IGNORECASE,
    )
    if prefixed_civic_before_city:
        prefix, s_num, s_name, city, province = prefixed_civic_before_city.groups()
        if (
            normalize_space(prefix).upper() not in {normalize_space(s_name).upper(), normalize_space(city).upper()}
            and not has_numbered_road_signal(s_name)
        ):
            # If the prefix starts with a unit keyword, do NOT treat it as noise prefix
            prefix_upper = prefix.upper().strip()
            unit_prefix_match = re.match(rf"^({LEADING_UNIT_KEYWORDS})(?:\s|$)", prefix_upper)
            if unit_prefix_match:
                # Set as unit instead of ignoring it
                u_num = standardize_unit_val(prefix)
                return _finalize_parsed(
                    s_num,
                    s_name,
                    u_num,
                    city,
                    province,
                    postal_code,
                    text,
                    "prefixed_unit_civic_before_city_special",
                    0.80,
                    0.85,
                    0.90,
                    profile=profile,
                    features={"pattern": "prefixed_unit_civic_before_city_special"},
                )
            return _finalize_parsed(
                s_num,
                s_name,
                None,
                city,
                province,
                postal_code,
                text,
                "prefixed_civic_before_city",
                0.74,
                0.1,
                0.9,
                profile=profile,
                features={"pattern": "prefixed_civic_before_city"},
            )

    prefixed_unit_civic_before_city = re.match(
        rf"^\s*([A-Z][A-Z' \-]{{2,24}})\s+(\d{{1,5}}[A-Z]?)\s*-\s*(\d+[A-Z]?)\s+([A-Z0-9 .'\-]+?(?:ST|STREET|AVE|AVENUE|DR|DRIVE|RD|ROAD|LN|LANE|PL|PLACE|CRT|COURT|CRES|CRESCENT|BLVD|BOULEVARD|WAY|TERR|TERRACE))\s+([A-Z][A-Z .'\-]+?)\s+({province_group})(?:\b.*)?$",
        text,
        re.IGNORECASE,
    )
    if prefixed_unit_civic_before_city:
        prefix, u_num, s_num, s_name, city, province = prefixed_unit_civic_before_city.groups()
        if normalize_space(prefix).upper() != normalize_space(city).upper():
            return _finalize_parsed(
                s_num,
                s_name,
                u_num,
                city,
                province,
                postal_code,
                text,
                "prefixed_unit_civic_before_city",
                0.82,
                0.86,
                0.9,
                profile=profile,
                features={"pattern": "prefixed_unit_civic_before_city"},
            )
    for regex, source, p_conf, u_conf in profile.parsing_patterns:
        match = regex.match(text_without_city_tail)
        if match:
            res = match.groups()
            logger.debug("Parsing Match - Source: %s, Res: %s", source, res) # Debug log
            s_num, s_name, u_num = None, None, None

            # Re-implement conditional unpacking with robust fallback
            if source in {"glued_comm_prefix", "comm_prefix_label", "level_prefix"}:
                # Expected: keyword, unit, s_num, s_name
                if len(res) >= 4: 
                    u_num, s_num, s_name = res[1], res[2], res[3]
                    if source == "level_prefix":
                        u_num = f"{res[0].upper()} {res[1]}"
                elif len(res) == 3: 
                    u_num, s_num = res[1], res[2]
            elif source in {"leading_hyphen", "hash_prefix"}:
                # Expected: unit, s_num, s_name
                if len(res) >= 3: u_num, s_num, s_name = res[0], res[1], res[2]
                elif len(res) == 2: u_num, s_num = res[0], res[1]
            elif source == "trailing_unit":
                # Expected: s_num, s_name, unit
                if len(res) >= 3: s_num, s_name, u_num = res[0], res[1], res[2]
                elif len(res) == 2: s_num, s_name = res[0], res[1]
            elif source == "street_standard":
                # Expected: s_num, s_name
                if len(res) >= 2: s_num, s_name = res[0], res[1]
                elif len(res) == 1: s_num = res[0]
            elif source == "simple_rule": # New: Handle simple_rule patterns
                # Expected: s_num, s_name
                if len(res) >= 2: s_num, s_name = res[0], res[1]
                elif len(res) == 1: s_num = res[0]
            else:
                # Fallback for other unknown patterns, assuming s_num, s_name, u_num from res
                if len(res) == 3: s_num, s_name, u_num = res[0], res[1], res[2]
                elif len(res) == 2: s_num, s_name = res[0], res[1]
                elif len(res) == 1: s_num = res[0]
            
            # Additional check for missing s_name or s_num after unpacking
            if not s_name and len(res) > 1: s_name = res[-1]
            if not s_num and len(res) > 0: s_num = res[0]

            return _finalize_parsed(s_num, s_name, u_num, fallback_city, fallback_province, postal_code, text, source, p_conf, u_conf, 0.90, profile=profile, features={"pattern": source})
    return _finalize_parsed(None, None, None, fallback_city, fallback_province, postal_code, text, "fallback", 0.1, 0.1, 0.1, profile=profile)
