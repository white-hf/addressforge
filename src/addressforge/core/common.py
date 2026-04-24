from __future__ import annotations

import atexit
import ctypes
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
import re
from pathlib import Path
from threading import Lock
from typing import Any, Iterable

import mysql.connector
from mysql.connector import Error

from .config import (
    ADDRESS_V2_DATABASE,
    ADDRESS_V2_DEFAULT_LOOKBACK_SECONDS,
    MYSQL_CONFIG,
)
from .utils import logger


POSTAL_RE = re.compile(r"([A-Za-z]\d[A-Za-z])\s?(\d[A-Za-z]\d)")
STREET_RE = re.compile(
    r"^\s*(?:(?P<unit>(?:apt|apartment|unit|suite|ste|#)\s*[\w-]+)\s+)?"
    r"(?P<number>\d+[A-Za-z]?)\s+(?P<street>[^,]+)",
    re.IGNORECASE,
)
COUNTRY_TOKENS = {"CA", "CANADA"}
PROVINCE_TOKENS = {"NS", "NB", "PE", "NL", "QC", "ON", "MB", "SK", "AB", "BC"}
STREET_TYPE_ALIASES = {
    "ALLEY": "ALY",
    "ALY": "ALY",
    "AVENUE": "AVE",
    "AVE": "AVE",
    "BOULEVARD": "BLVD",
    "BLVD": "BLVD",
    "CIRCLE": "CIR",
    "CIR": "CIR",
    "COMMON": "CMN",
    "CMN": "CMN",
    "COURT": "CT",
    "CT": "CT",
    "CRESCENT": "CRES",
    "CRES": "CRES",
    "DRIVE": "DR",
    "DR": "DR",
    "HIGHWAY": "HWY",
    "HWY": "HWY",
    "LANE": "LN",
    "LN": "LN",
    "PARKWAY": "PKWY",
    "PKWY": "PKWY",
    "PKY": "PKWY",
    "PLACE": "PL",
    "PL": "PL",
    "POINT": "PT",
    "PT": "PT",
    "ROAD": "RD",
    "RD": "RD",
    "SQUARE": "SQ",
    "SQ": "SQ",
    "STREET": "ST",
    "ST": "ST",
    "TERRACE": "TER",
    "TER": "TER",
    "TRAIL": "TRL",
    "TRL": "TRL",
    "WAY": "WAY",
}
STREET_DIRECTION_ALIASES = {
    "NORTH": "N",
    "N": "N",
    "SOUTH": "S",
    "S": "S",
    "EAST": "E",
    "E": "E",
    "WEST": "W",
    "W": "W",
    "NORTHEAST": "NE",
    "NE": "NE",
    "NORTHWEST": "NW",
    "NW": "NW",
    "SOUTHEAST": "SE",
    "SE": "SE",
    "SOUTHWEST": "SW",
    "SW": "SW",
}
UNIT_PREFIX_RE = re.compile(r"^(?:APT|APARTMENT|UNIT|SUITE|STE|#)\s*([A-Z0-9-]{1,10})\s+(\d+[A-Z]?)\s+(.+)$")
LEADING_HYPHEN_RE = re.compile(r"^([A-Z0-9]{1,10})\s*-\s*(\d+[A-Z]?)\s+(.+)$")
TRAILING_KEYWORD_RE = re.compile(r"^(\d+[A-Z]?)\s+(.+?)\s+(?:APT|APARTMENT|UNIT|SUITE|STE|#)\s*([A-Z0-9-]{1,10})$")
HASH_PREFIX_RE = re.compile(r"^#\s*([A-Z0-9-]{1,10})\s+(\d+[A-Z]?)\s+(.+)$")
STREET_SUFFIX_TRAILING_RE = re.compile(
    r"^(\d+[A-Z]?)\s+(.+?\b(?:ST|STREET|RD|ROAD|AVE|AVENUE|DR|DRIVE|LN|LANE|CT|COURT|BLVD|BOULEVARD|CRES|CRESCENT|PL|PLACE|WAY|HWY|HIGHWAY))\s+([A-Z0-9-]{1,10})$"
)
DOUBLE_NUMBER_PREFIX_RE = re.compile(r"^(\d{1,5})\s+(\d{1,5}[A-Z]?)\s+(.+)$")
EMBEDDED_UNIT_TOKEN_RE = re.compile(
    r"^(\d+[A-Z]?)\s+(.+?)\s+(?:BLDG|BUILDING|UNIT|APT|APARTMENT|SUITE|STE)\s*([A-Z0-9-]{1,10})$"
)
INLINE_HYPHEN_RE = re.compile(r"^(\d+[A-Z]?)\s+([A-Z0-9-]+)-([A-Z0-9-]+)\s+(.+)$")
POBOX_RE = re.compile(r"\b(?:P\.?\s*O\.?\s*)?BOX\s+\d+\b")
RURAL_ROUTE_RE = re.compile(r"\b(?:RR\s*\d+|RURAL\s+ROUTE|SITE\s+\d+|COMP\s+\d+|GENERAL\s+DELIVERY)\b")
LIBPOSTAL_CANDIDATE_PATHS = (
    "/opt/homebrew/lib/libpostal.dylib",
    "/usr/local/lib/libpostal.dylib",
)


class _LibpostalParserOptions(ctypes.Structure):
    _fields_ = [
        ("language", ctypes.c_char_p),
        ("country", ctypes.c_char_p),
    ]


class _LibpostalParserResponse(ctypes.Structure):
    _fields_ = [
        ("num_components", ctypes.c_size_t),
        ("components", ctypes.POINTER(ctypes.c_char_p)),
        ("labels", ctypes.POINTER(ctypes.c_char_p)),
    ]


_LIBPOSTAL = None
_LIBPOSTAL_READY = False
_LIBPOSTAL_LOCK = Lock()
_LIBPOSTAL_TEARDOWN_REGISTERED = False
LOCK_RETRY_ERRNOS = {1205, 1213}
ETL_RUN_TYPES = [
    "ingestion",
    "history_import",
    "normalize",
    "parse",
    "evidence_aggregate",
    "publish",
    "user_profile",
    "ml_export",
    "incremental_pipeline",
]


def _mysql_config(database: str | None = ADDRESS_V2_DATABASE) -> dict[str, Any]:
    cfg = dict(MYSQL_CONFIG)
    cfg["raise_on_warnings"] = False
    if database is not None:
        cfg["database"] = database
    else:
        cfg.pop("database", None)
    return cfg


def get_v2_connection(database: str | None = ADDRESS_V2_DATABASE):
    conn = mysql.connector.connect(**_mysql_config(database))
    conn.autocommit = True
    return conn


@contextmanager
def db_cursor(dictionary: bool = False, database: str | None = ADDRESS_V2_DATABASE):
    conn = get_v2_connection(database)
    cursor = conn.cursor(dictionary=dictionary)
    try:
        yield conn, cursor
    finally:
        cursor.close()
        conn.close()


def execute_sql_script(script_path: str | Path, database: str | None = None) -> None:
    sql = Path(script_path).read_text(encoding="utf-8")
    execute_sql_text(sql, database=database)


def execute_sql_text(sql: str, database: str | None = ADDRESS_V2_DATABASE) -> None:
    statements = [segment.strip() for segment in sql.split(";") if segment.strip()]
    with get_v2_connection(database) as conn:
        cursor = conn.cursor()
        try:
            for statement in statements:
                cursor.execute(statement)
            conn.commit()
        finally:
            cursor.close()


def executemany_chunked(
    cursor: Any,
    query: str,
    rows: Iterable[tuple[Any, ...]],
    chunk_size: int = 500,
) -> int:
    def _is_retryable(exc: BaseException) -> bool:
        return isinstance(exc, Error) and getattr(exc, "errno", None) in LOCK_RETRY_ERRNOS

    def _execute_batch(batch: list[tuple[Any, ...]], depth: int = 0) -> int:
        retries = 4
        for attempt in range(retries):
            try:
                cursor.executemany(query, batch)
                return len(batch)
            except Exception as exc:  # noqa: BLE001
                if not _is_retryable(exc):
                    raise
                if len(batch) <= 50 or depth >= 3:
                    if attempt == retries - 1:
                        raise
                    time.sleep(0.5 * (attempt + 1))
                    continue
                midpoint = max(1, len(batch) // 2)
                left = _execute_batch(batch[:midpoint], depth + 1)
                right = _execute_batch(batch[midpoint:], depth + 1)
                return left + right
        return 0

    total = 0
    batch: list[tuple[Any, ...]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= chunk_size:
            total += _execute_batch(batch)
            batch.clear()
    if batch:
        total += _execute_batch(batch)
    return total


def create_run(run_type: str, parser_version: str | None = None, scoring_version: str | None = None, notes: str | None = None) -> int:
    query = """
        INSERT INTO etl_run (run_type, parser_version, scoring_version, status, notes)
        VALUES (%s, %s, %s, 'running', %s)
    """
    with db_cursor() as (conn, cursor):
        cursor.execute(query, (run_type, parser_version, scoring_version, notes))
        conn.commit()
        return int(cursor.lastrowid)


def stable_holdout_bucket(*parts: Any, modulo: int = 5) -> int:
    values = []
    for part in parts:
        if part is None:
            continue
        text = str(part).strip().lower()
        if text:
            values.append(text)
    if not values:
        return 0
    digest = hashlib.sha256("||".join(values).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % max(modulo, 2)


def finish_run(run_id: int, status: str, notes: str | None = None) -> None:
    query = """
        UPDATE etl_run
        SET status = %s, finished_at = NOW(), notes = COALESCE(%s, notes)
        WHERE run_id = %s
    """
    with db_cursor() as (conn, cursor):
        cursor.execute(query, (status, notes, run_id))
        conn.commit()


def ensure_etl_run_types() -> None:
    query = """
        SELECT COLUMN_TYPE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = 'etl_run'
          AND COLUMN_NAME = 'run_type'
    """
    with db_cursor(dictionary=True) as (conn, cursor):
        cursor.execute(query, (ADDRESS_V2_DATABASE,))
        row = cursor.fetchone()
        if not row:
            return
        column_type = str(row["COLUMN_TYPE"]).lower()
        if all(run_type in column_type for run_type in ETL_RUN_TYPES):
            return
        enum_sql = ",\n                        ".join(f"'{run_type}'" for run_type in ETL_RUN_TYPES)
        cursor.execute(
            f"""
            ALTER TABLE etl_run MODIFY COLUMN run_type ENUM(
                {enum_sql}
            ) NOT NULL
            """
        )
        conn.commit()


def get_ingestion_cursor(source_system: str, cursor_type: str) -> str | None:
    query = """
        SELECT cursor_value
        FROM source_ingestion_cursor
        WHERE source_system = %s AND cursor_type = %s
    """
    with db_cursor(dictionary=True) as (_, cursor):
        cursor.execute(query, (source_system, cursor_type))
        row = cursor.fetchone()
        return row["cursor_value"] if row else None


def set_ingestion_cursor(source_system: str, cursor_type: str, cursor_value: str) -> None:
    query = """
        INSERT INTO source_ingestion_cursor (source_system, cursor_type, cursor_value)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            cursor_value = VALUES(cursor_value),
            last_success_at = NOW()
    """
    with db_cursor() as (conn, cursor):
        cursor.execute(query, (source_system, cursor_type, cursor_value))
        conn.commit()


def default_start_timestamp() -> int:
    return int((datetime.utcnow() - timedelta(seconds=ADDRESS_V2_DEFAULT_LOOKBACK_SECONDS)).timestamp())


def normalize_space(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def normalize_recipient_name(value: str | None) -> str | None:
    text = normalize_space(value)
    if not text:
        return None
    text = re.sub(r"[^A-Za-z0-9 ]+", "", text).upper()
    text = normalize_space(text)
    return text or None


def normalize_phone_number(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D+", "", value)
    if not digits:
        return None
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) < 10:
        return None
    return digits


def canonicalize_unit_number(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = normalize_space(value)
    if not cleaned:
        return None
    cleaned = re.sub(r"[\.,;]+$", "", cleaned)
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = re.sub(r"^(apt|apartment|unit|suite|ste|#)\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = normalize_space(cleaned)
    cleaned = cleaned.lstrip("#")
    cleaned = normalize_space(cleaned).upper()
    return cleaned or None


def generate_contact_key_v2(recipient_name: str | None, recipient_phone: str | None) -> str | None:
    normalized_phone = normalize_phone_number(recipient_phone)
    if not normalized_phone:
        return None
    normalized_name = normalize_recipient_name(recipient_name) or ""
    return hashlib.sha256(f"{normalized_phone}|{normalized_name}".encode("utf-8")).hexdigest()


def generate_recipient_cluster_id(
    recipient_name: str | None,
    recipient_phone: str | None,
    postal_code: str | None = None,
    city: str | None = None,
    province: str | None = None,
    legacy_user_hash: str | None = None,
) -> tuple[str | None, str | None]:
    normalized_phone = normalize_phone_number(recipient_phone)
    normalized_name = normalize_recipient_name(recipient_name)
    normalized_postal = canonical_postal_code(postal_code)
    normalized_city = normalize_city(city)
    normalized_province = normalize_province(province)

    if normalized_phone:
        token = f"phone|{normalized_phone}"
        return hashlib.sha256(token.encode("utf-8")).hexdigest(), "phone"

    if normalized_name and (normalized_postal or normalized_city or normalized_province):
        token = "|".join(
            [
                "name_locality",
                normalized_name,
                normalized_postal or "",
                normalized_city or "",
                normalized_province or "",
            ]
        )
        return hashlib.sha256(token.encode("utf-8")).hexdigest(), "name_locality"

    if normalized_name:
        token = f"name|{normalized_name}"
        return hashlib.sha256(token.encode("utf-8")).hexdigest(), "name"

    if legacy_user_hash:
        token = f"legacy|{legacy_user_hash}"
        return hashlib.sha256(token.encode("utf-8")).hexdigest(), "legacy"

    return None, None


def canonical_postal_code(value: str | None) -> str | None:
    if not value:
        return None
    match = POSTAL_RE.search(value)
    if not match:
        return None
    return f"{match.group(1).upper()} {match.group(2).upper()}"


def normalize_city(value: str | None) -> str | None:
    text = normalize_space(value)
    return text.title() if text else None


def normalize_province(value: str | None) -> str | None:
    text = normalize_space(value).replace(".", "").upper()
    if not text:
        return None
    if len(text) == 2:
        return text
    provinces = {
        "NOVA SCOTIA": "NS",
        "NEW BRUNSWICK": "NB",
        "PRINCE EDWARD ISLAND": "PE",
        "NEWFOUNDLAND AND LABRADOR": "NL",
        "ONTARIO": "ON",
        "QUEBEC": "QC",
        "ALBERTA": "AB",
        "BRITISH COLUMBIA": "BC",
        "MANITOBA": "MB",
        "SASKATCHEWAN": "SK",
    }
    return provinces.get(text)


def normalize_street_name(value: str | None) -> str | None:
    text = normalize_space(value)
    if not text:
        return None
    normalized_tokens: list[str] = []
    for token in text.upper().split(" "):
        cleaned = token.replace(".", "")
        if not cleaned:
            continue
        normalized_tokens.append(
            STREET_DIRECTION_ALIASES.get(
                cleaned,
                STREET_TYPE_ALIASES.get(cleaned, cleaned),
            )
        )
    return " ".join(normalized_tokens) if normalized_tokens else None


def build_base_address_key(street_number: str | None, street_name: str | None, city: str | None, province: str | None, postal_code: str | None) -> str:
    parts = [
        normalize_space(street_number).upper(),
        normalize_street_name(street_name) or "",
        (normalize_city(city) or "").upper(),
        (normalize_province(province) or "").upper(),
        (canonical_postal_code(postal_code) or normalize_space(postal_code).upper()),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def build_full_address_key(base_address_key: str, unit_number: str | None) -> str:
    return hashlib.sha256(f"{base_address_key}|{canonicalize_unit_number(unit_number) or ''}".encode("utf-8")).hexdigest()


def simple_parse_address(raw_address_text: str, fallback_postal: str | None = None, fallback_city: str | None = None, fallback_province: str | None = None) -> dict[str, str | None]:
    text = normalize_space(raw_address_text)
    postal_code = canonical_postal_code(fallback_postal or text)
    match = STREET_RE.match(text)
    street_number = None
    street_name = None
    unit_number = None
    if match:
        street_number = normalize_space(match.group("number")).upper()
        street_name = normalize_street_name(match.group("street"))
        unit_token = match.group("unit")
        if unit_token:
            unit_number = canonicalize_unit_number(unit_token)

    city = normalize_city(fallback_city) or "Halifax"
    province = normalize_province(fallback_province) or "NS"
    base_key = build_base_address_key(street_number, street_name, city, province, postal_code)
    full_key = build_full_address_key(base_key, unit_number)
    return {
        "normalized_text": text,
        "street_number": street_number,
        "street_name": normalize_street_name(street_name),
        "unit_number": unit_number,
        "city": city,
        "province": province,
        "postal_code": postal_code,
        "base_address_key": base_key,
        "full_address_key": full_key,
    }


def _split_commas(text: str) -> list[str]:
    return [segment.strip() for segment in text.split(",") if segment.strip()]


def _strip_canadian_tail(text: str) -> tuple[str, str | None, str | None, str | None]:
    parts = _split_commas(text)
    postal_code = canonical_postal_code(text)
    city = None
    province = None
    kept: list[str] = []
    for part in parts:
        upper = normalize_space(part).upper()
        if canonical_postal_code(part):
            postal_code = canonical_postal_code(part)
            continue
        if upper in COUNTRY_TOKENS:
            continue
        norm_province = normalize_province(part)
        if norm_province and upper in PROVINCE_TOKENS:
            province = norm_province
            continue
        kept.append(part)
    if len(kept) >= 2:
        city = normalize_city(kept[-1])
        kept = kept[:-1]
    street_line = normalize_space(", ".join(kept) if kept else text)
    return street_line, city, province, postal_code


def _finalize_parsed(street_number: str | None, street_name: str | None, unit_number: str | None, city: str | None, province: str | None, postal_code: str | None, normalized_text: str, unit_source: str | None, parse_conf: float, unit_conf: float, postal_conf: float) -> dict[str, str | float | None]:
    base_key = build_base_address_key(street_number, street_name, city, province, postal_code)
    full_key = build_full_address_key(base_key, unit_number)
    return {
        "normalized_text": normalized_text,
        "street_number": street_number.upper() if street_number else None,
        "street_name": normalize_street_name(street_name),
        "unit_number": canonicalize_unit_number(unit_number),
        "city": normalize_city(city) or "Halifax",
        "province": normalize_province(province) or "NS",
        "postal_code": postal_code,
        "base_address_key": base_key,
        "full_address_key": full_key,
        "unit_source": unit_source,
        "parse_confidence": parse_conf,
        "unit_confidence": unit_conf,
        "postal_confidence": postal_conf,
    }


def hybrid_canadian_parse_address(raw_address_text: str, fallback_postal: str | None = None, fallback_city: str | None = None, fallback_province: str | None = None) -> dict[str, str | float | None]:
    text = normalize_space(raw_address_text).upper()
    if POBOX_RE.search(text) or RURAL_ROUTE_RE.search(text):
        simple = simple_parse_address(
            raw_address_text=text,
            fallback_postal=fallback_postal,
            fallback_city=fallback_city,
            fallback_province=fallback_province,
        )
        return _finalize_parsed(
            street_number=simple["street_number"],
            street_name=simple["street_name"],
            unit_number=simple["unit_number"],
            city=simple["city"],
            province=simple["province"],
            postal_code=simple["postal_code"],
            normalized_text=text,
            unit_source="non_civic_route",
            parse_conf=0.20,
            unit_conf=0.05,
            postal_conf=0.80 if simple["postal_code"] else 0.20,
        )
    street_line, city, province, postal_code = _strip_canadian_tail(text)
    city = city or fallback_city
    province = province or fallback_province
    postal_code = postal_code or canonical_postal_code(fallback_postal)

    for regex, source, parse_conf, unit_conf in (
        (LEADING_HYPHEN_RE, "leading_hyphen", 0.96, 0.98),
        (UNIT_PREFIX_RE, "unit_prefix", 0.95, 0.97),
        (HASH_PREFIX_RE, "hash_prefix", 0.95, 0.97),
        (TRAILING_KEYWORD_RE, "keyword_global", 0.94, 0.96),
        (STREET_SUFFIX_TRAILING_RE, "street_suffix_trailing", 0.90, 0.88),
        (EMBEDDED_UNIT_TOKEN_RE, "embedded_unit_token", 0.92, 0.90),
    ):
        match = regex.match(street_line)
        if not match:
            continue
        if source in {"leading_hyphen", "unit_prefix", "hash_prefix"}:
            unit_number, street_number, street_name = match.group(1), match.group(2), match.group(3)
        elif source == "keyword_global":
            street_number, street_name, unit_number = match.group(1), match.group(2), match.group(3)
        else:
            street_number, street_name, unit_number = match.group(1), match.group(2), match.group(3)
        return _finalize_parsed(
            street_number=street_number,
            street_name=street_name,
            unit_number=unit_number,
            city=city,
            province=province,
            postal_code=postal_code,
            normalized_text=text,
            unit_source=source,
            parse_conf=parse_conf,
            unit_conf=unit_conf,
            postal_conf=0.90 if postal_code else 0.40,
        )

    match = DOUBLE_NUMBER_PREFIX_RE.match(street_line)
    if match:
        first_number, street_number, street_name = match.group(1), match.group(2), match.group(3)
        if postal_code and first_number in postal_code.replace(" ", ""):
            pass
        else:
            return _finalize_parsed(
                street_number=street_number,
                street_name=street_name,
                unit_number=first_number,
                city=city,
                province=province,
                postal_code=postal_code,
                normalized_text=text,
                unit_source="double_number_prefix",
                parse_conf=0.88,
                unit_conf=0.84,
                postal_conf=0.90 if postal_code else 0.30,
            )

    match = INLINE_HYPHEN_RE.match(street_line)
    if match:
        street_number, first_token, second_token, street_name = match.group(1), match.group(2), match.group(3), match.group(4)
        inferred_unit = second_token if not first_token.isdigit() else first_token
        return _finalize_parsed(
            street_number=street_number,
            street_name=f"{first_token if inferred_unit == second_token else second_token} {street_name}",
            unit_number=inferred_unit,
            city=city,
            province=province,
            postal_code=postal_code,
            normalized_text=text,
            unit_source="inline_hyphen",
            parse_conf=0.84,
            unit_conf=0.80,
            postal_conf=0.90 if postal_code else 0.25,
        )

    simple = simple_parse_address(
        raw_address_text=text,
        fallback_postal=postal_code,
        fallback_city=city,
        fallback_province=province,
    )
    unit_source = "simple_fallback" if simple["unit_number"] else None
    return _finalize_parsed(
        street_number=simple["street_number"],
        street_name=simple["street_name"],
        unit_number=simple["unit_number"],
        city=simple["city"],
        province=simple["province"],
        postal_code=simple["postal_code"],
        normalized_text=text,
        unit_source=unit_source,
        parse_conf=0.82 if simple["street_number"] and simple["street_name"] else 0.25,
        unit_conf=0.80 if simple["unit_number"] else 0.10,
        postal_conf=0.90 if simple["postal_code"] else 0.20,
    )


def _load_libpostal() -> ctypes.CDLL | None:
    global _LIBPOSTAL
    if _LIBPOSTAL is not None:
        return _LIBPOSTAL
    for path in LIBPOSTAL_CANDIDATE_PATHS:
        if not Path(path).exists():
            continue
        try:
            library = ctypes.CDLL(path)
            library.libpostal_setup.restype = ctypes.c_bool
            library.libpostal_setup_parser.restype = ctypes.c_bool
            library.libpostal_teardown.restype = None
            library.libpostal_teardown_parser.restype = None
            library.libpostal_get_address_parser_default_options.restype = _LibpostalParserOptions
            library.libpostal_parse_address.argtypes = [ctypes.c_char_p, _LibpostalParserOptions]
            library.libpostal_parse_address.restype = ctypes.POINTER(_LibpostalParserResponse)
            library.libpostal_address_parser_response_destroy.argtypes = [ctypes.POINTER(_LibpostalParserResponse)]
            library.libpostal_address_parser_response_destroy.restype = None
            _LIBPOSTAL = library
            return _LIBPOSTAL
        except OSError as exc:
            logger.warning("Failed loading libpostal from %s: %s", path, exc)
    return None


def _teardown_libpostal() -> None:
    global _LIBPOSTAL_READY
    if _LIBPOSTAL is None or not _LIBPOSTAL_READY:
        return
    try:
        _LIBPOSTAL.libpostal_teardown_parser()
        _LIBPOSTAL.libpostal_teardown()
    except Exception:
        logger.exception("libpostal teardown failed")
    finally:
        _LIBPOSTAL_READY = False


def _ensure_libpostal_ready() -> bool:
    global _LIBPOSTAL_READY
    global _LIBPOSTAL_TEARDOWN_REGISTERED
    if _LIBPOSTAL_READY:
        return True
    with _LIBPOSTAL_LOCK:
        if _LIBPOSTAL_READY:
            return True
        library = _load_libpostal()
        if library is None:
            return False
        if not library.libpostal_setup():
            logger.warning("libpostal_setup() returned false")
            return False
        if not library.libpostal_setup_parser():
            logger.warning("libpostal_setup_parser() returned false")
            library.libpostal_teardown()
            return False
        _LIBPOSTAL_READY = True
        if not _LIBPOSTAL_TEARDOWN_REGISTERED:
            atexit.register(_teardown_libpostal)
            _LIBPOSTAL_TEARDOWN_REGISTERED = True
        return True


def _libpostal_extract_components(response: _LibpostalParserResponse) -> dict[str, str]:
    components: dict[str, str] = {}
    for index in range(response.num_components):
        label = response.labels[index].decode("utf-8") if response.labels[index] else ""
        value = response.components[index].decode("utf-8") if response.components[index] else ""
        if not label or not value or label in components:
            continue
        components[label] = normalize_space(value)
    return components


def _normalize_unit_token(value: str | None) -> str | None:
    if not value:
        return None
    return canonicalize_unit_number(value)


def _repair_libpostal_components(street_number: str | None, street_name: str | None, unit_number: str | None, city: str | None) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    repair_source = None
    normalized_unit = _normalize_unit_token(unit_number)
    if street_number and not normalized_unit:
        hyphen_match = re.match(r"^([A-Z0-9]{1,10})-(\d+[A-Z]?)$", street_number.upper())
        if hyphen_match:
            normalized_unit = hyphen_match.group(1)
            street_number = hyphen_match.group(2)
            repair_source = "libpostal_house_number_hyphen"

    normalized_city = normalize_city(city)
    if normalized_city and street_name:
        city_tokens = normalized_city.upper().split(" ")
        if len(city_tokens) >= 2 and city_tokens[0] in STREET_DIRECTION_ALIASES:
            direction = STREET_DIRECTION_ALIASES[city_tokens[0]]
            normalized_street = normalize_street_name(street_name) or street_name
            street_tokens = normalized_street.split(" ")
            if street_tokens and street_tokens[-1] not in STREET_DIRECTION_ALIASES.values():
                street_name = f"{normalized_street} {direction}"
                normalized_city = normalize_city(" ".join(city_tokens[1:]))
                repair_source = repair_source or "libpostal_directional_city"

    return street_number, street_name, normalized_unit, normalized_city, repair_source


def libpostal_parse_address(raw_address_text: str, fallback_postal: str | None = None, fallback_city: str | None = None, fallback_province: str | None = None) -> dict[str, str | float | None]:
    if not _ensure_libpostal_ready():
        simple = simple_parse_address(
            raw_address_text=raw_address_text,
            fallback_postal=fallback_postal,
            fallback_city=fallback_city,
            fallback_province=fallback_province,
        )
        return _finalize_parsed(
            street_number=simple["street_number"],
            street_name=simple["street_name"],
            unit_number=simple["unit_number"],
            city=simple["city"],
            province=simple["province"],
            postal_code=simple["postal_code"],
            normalized_text=normalize_space(raw_address_text).upper(),
            unit_source="libpostal_unavailable_fallback",
            parse_conf=0.40 if simple["street_number"] and simple["street_name"] else 0.18,
            unit_conf=0.45 if simple["unit_number"] else 0.08,
            postal_conf=0.70 if simple["postal_code"] else 0.20,
        )

    options = _LIBPOSTAL.libpostal_get_address_parser_default_options()
    options.country = b"ca"
    response_ptr = _LIBPOSTAL.libpostal_parse_address(normalize_space(raw_address_text).encode("utf-8"), options)
    if not response_ptr:
        return hybrid_canadian_parse_address(
            raw_address_text=raw_address_text,
            fallback_postal=fallback_postal,
            fallback_city=fallback_city,
            fallback_province=fallback_province,
        )

    try:
        parsed = _libpostal_extract_components(response_ptr.contents)
    finally:
        _LIBPOSTAL.libpostal_address_parser_response_destroy(response_ptr)

    street_number = parsed.get("house_number")
    street_name = parsed.get("road")
    unit_number = parsed.get("unit")
    city = (
        parsed.get("city")
        or parsed.get("city_district")
        or parsed.get("suburb")
        or parsed.get("residential")
        or fallback_city
    )
    province = parsed.get("state") or fallback_province
    postal_code = canonical_postal_code(parsed.get("postcode") or fallback_postal or raw_address_text)
    street_number, street_name, unit_number, city, repair_source = _repair_libpostal_components(
        street_number=street_number,
        street_name=street_name,
        unit_number=unit_number,
        city=city,
    )
    unit_source = "libpostal_unit" if unit_number else None
    if repair_source:
        unit_source = repair_source if unit_source is None else f"{unit_source}+{repair_source}"
    parse_conf = 0.20
    if street_number and street_name:
        parse_conf = 0.86
        if city:
            parse_conf += 0.04
        if province:
            parse_conf += 0.02
        if postal_code:
            parse_conf += 0.03
    elif street_name:
        parse_conf = 0.52
    if POBOX_RE.search(normalize_space(raw_address_text).upper()) or RURAL_ROUTE_RE.search(normalize_space(raw_address_text).upper()):
        parse_conf = min(parse_conf, 0.35)

    return _finalize_parsed(
        street_number=street_number,
        street_name=street_name,
        unit_number=unit_number,
        city=city,
        province=province,
        postal_code=postal_code,
        normalized_text=normalize_space(raw_address_text).upper(),
        unit_source=unit_source,
        parse_conf=min(round(parse_conf, 4), 0.95),
        unit_conf=0.93 if unit_number else 0.08,
        postal_conf=0.95 if postal_code else 0.22,
    )


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    phi1 = math_radians(lat1)
    phi2 = math_radians(lat2)
    d_phi = math_radians(lat2 - lat1)
    d_lambda = math_radians(lon2 - lon1)
    a = (
        math_sin(d_phi / 2) ** 2
        + math_cos(phi1) * math_cos(phi2) * math_sin(d_lambda / 2) ** 2
    )
    c = 2 * math_atan2(math_sqrt(a), math_sqrt(1 - a))
    return radius * c


def math_radians(value: float) -> float:
    from math import radians

    return radians(value)


def math_sin(value: float) -> float:
    from math import sin

    return sin(value)


def math_cos(value: float) -> float:
    from math import cos

    return cos(value)


def math_sqrt(value: float) -> float:
    from math import sqrt

    return sqrt(value)


def math_atan2(y: float, x: float) -> float:
    from math import atan2

    return atan2(y, x)


def dumps_payload(payload: dict[str, Any]) -> str:
    def _default(value: Any):
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime,)):
            return value.isoformat(sep=" ")
        return str(value)

    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=_default)


def fetch_all(query: str, params: Iterable[Any] | None = None) -> list[dict[str, Any]]:
    with db_cursor(dictionary=True) as (_, cursor):
        cursor.execute(query, params or ())
        return list(cursor.fetchall())


def log_run_exception(run_id: int, exc: Exception) -> None:
    logger.exception("Run %s failed: %s", run_id, exc)
    finish_run(run_id, "failed", notes=str(exc))
