from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from addressforge.core.common import (
    canonicalize_unit_number,
    db_cursor,
    fetch_all,
    dumps_payload,
    normalize_city,
    normalize_space,
    normalize_street_name,
)
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.core.utils import logger


_CANADA_PROVINCES = {
    "AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT",
}
_CANADA_POSTAL_RE = re.compile(r"\b[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z]\d[ABCEGHJ-NPRSTV-Z]\d\b", re.IGNORECASE)
_UNIT_WORDS = {"UNIT", "APT", "APT.", "APARTMENT", "SUITE", "STE", "ROOM", "RM", "FLOOR", "FL", "BASEMENT", "LOWER", "UPPER"}
_STREET_SUFFIX_WORDS = {
    "RD", "ROAD", "ST", "STREET", "AVE", "AVENUE", "BLVD", "BOULEVARD", "LN", "LANE",
    "DR", "DRIVE", "CRT", "COURT", "CT", "CIRCLE", "CIR", "WAY", "PKWY", "HIGHWAY", "HWY",
    "TRL", "TRAIL", "PL", "PLACE", "TER", "TERRACE",
}
_STREET_SUFFIX_NORMALIZATION = {
    "ROAD": "RD",
    "STREET": "ST",
    "AVENUE": "AVE",
    "BOULEVARD": "BLVD",
    "LANE": "LN",
    "DRIVE": "DR",
    "COURT": "CRT",
    "CIRCLE": "CIR",
    "HIGHWAY": "HWY",
    "TRAIL": "TRL",
    "PLACE": "PL",
    "TERRACE": "TER",
}
_PROVINCE_NAME_TO_CODE = {
    "ALBERTA": "AB",
    "BRITISH COLUMBIA": "BC",
    "MANITOBA": "MB",
    "NEW BRUNSWICK": "NB",
    "NEWFOUNDLAND": "NL",
    "NEWFOUNDLAND AND LABRADOR": "NL",
    "NOVA SCOTIA": "NS",
    "ONTARIO": "ON",
    "PRINCE EDWARD ISLAND": "PE",
    "QUEBEC": "QC",
    "SASKATCHEWAN": "SK",
    "NORTHWEST TERRITORIES": "NT",
    "NUNAVUT": "NU",
    "YUKON": "YT",
}
_LOCALITY_NOISE_WORDS = {"BUZZER", "CODE", "IS", "NO", "NUMBER"}
_UNIT_NORMALIZATION_NOISE_WORDS = {"NUMBER", "UNIT", "APT", "APARTMENT", "SUITE", "STE", "ROOM", "RM"}
_STRONG_UNIT_HINT_RE = re.compile(
    r"(?:\b(?:UNIT|APT|APARTMENT|SUITE|STE|ROOM|RM|FLOOR|FL|BASEMENT|LOWER|UPPER)\b\s*[#A-Z0-9-]*|#\s*[A-Z0-9]+)",
    re.IGNORECASE,
)


def _safe_json_loads(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _canonical_building_key(row: dict[str, Any]) -> tuple[str, bool]:
    resolved_ext_id = str(row.get("resolved_reference_external_id") or "").strip()
    if resolved_ext_id:
        return hashlib.sha256(
            f"REF|{row.get('country_code') or 'CA'}|{resolved_ext_id}".encode("utf-8")
        ).hexdigest(), True
    ref_data = _safe_json_loads(row.get("reference_json"))
    ext_id = str(ref_data.get("external_id") or "").strip()
    if ext_id:
        return hashlib.sha256(
            f"REF|{row.get('country_code') or 'CA'}|{ext_id}".encode("utf-8")
        ).hexdigest(), True
    return str(row.get("base_address_key") or ""), False


def _canonical_unit_key(building_key: str, unit_number: str | None) -> str | None:
    unit_value = _normalize_canonical_unit_value(unit_number)
    if not building_key or not unit_value:
        return None
    return hashlib.sha256(f"{building_key}|{unit_value}".encode("utf-8")).hexdigest()


def _normalize_canonical_unit_value(unit_value: str | None) -> str | None:
    normalized = canonicalize_unit_number(unit_value)
    if not normalized:
        return None
    tokens = [token for token in re.split(r"[\s-]+", normalized) if token]
    cleaned_tokens = [token for token in tokens if token not in _UNIT_NORMALIZATION_NOISE_WORDS]
    if not cleaned_tokens:
        return None
    if len(cleaned_tokens) == 2 and cleaned_tokens[0].isalpha() and cleaned_tokens[1].isdigit():
        return f"{cleaned_tokens[0]}{cleaned_tokens[1]}"
    if len(cleaned_tokens) == 2 and cleaned_tokens[0].isdigit() and cleaned_tokens[1].isalpha():
        return f"{cleaned_tokens[0]}{cleaned_tokens[1]}"
    return " ".join(cleaned_tokens)


def _parse_source_attribution(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
            if isinstance(loaded, list):
                return [str(item) for item in loaded if item not in (None, "")]
        except Exception:
            if value:
                return [value]
    return [str(value)]


def _merge_source_attribution_values(*values: Any) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in _parse_source_attribution(value):
            if item and item not in seen:
                seen.add(item)
                merged.append(item)
    return json.dumps(merged, ensure_ascii=False)


def _plan_canonical_unit_variant_merge(
    existing_rows: list[dict[str, Any]],
    normalized_unit: str,
    normalized_key: str,
) -> dict[str, Any]:
    target_row: dict[str, Any] | None = None
    duplicate_keys: list[str] = []
    source_values: list[Any] = []
    for row in existing_rows:
        row_key = str(row.get("unit_key") or "")
        row_value = _normalize_canonical_unit_value(row.get("unit_number"))
        if row_value != normalized_unit:
            continue
        source_values.append(row.get("source_attribution"))
        if row_key == normalized_key and target_row is None:
            target_row = row
            continue
        if row_key:
            duplicate_keys.append(row_key)
    return {
        "has_matching_variants": bool(target_row or duplicate_keys),
        "target_row": target_row,
        "duplicate_keys": duplicate_keys,
        "merged_source_attribution": _merge_source_attribution_values(*source_values),
    }


def _consolidate_canonical_unit_variants(
    cursor: Any,
    workspace_name: str,
    building_key: str,
    normalized_unit: str,
    normalized_key: str,
) -> None:
    cursor.execute(
        """
        SELECT unit_key, unit_number, source_attribution
        FROM canonical_unit
        WHERE workspace_name = %s
          AND building_key = %s
          AND is_active = 1
        """,
        (workspace_name, building_key),
    )
    existing_rows = cursor.fetchall() or []
    plan = _plan_canonical_unit_variant_merge(existing_rows, normalized_unit, normalized_key)
    if not plan["has_matching_variants"]:
        return
    merged_source = _merge_source_attribution_values(
        plan["merged_source_attribution"],
    )
    cursor.execute(
        """
        UPDATE canonical_unit
        SET unit_number = %s,
            source_attribution = %s,
            updated_at = NOW()
        WHERE workspace_name = %s
          AND unit_key = %s
        """,
        (normalized_unit, merged_source, workspace_name, normalized_key),
    )
    duplicate_keys = [key for key in plan["duplicate_keys"] if key != normalized_key]
    if duplicate_keys:
        placeholders = ", ".join(["%s"] * len(duplicate_keys))
        cursor.execute(
            f"""
            DELETE FROM canonical_unit
            WHERE workspace_name = %s
              AND unit_key IN ({placeholders})
            """,
            (workspace_name, *duplicate_keys),
        )


def _load_city_to_province_map(workspace_name: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    raw_rows = fetch_all(
        """
        SELECT city, province, COUNT(*) AS cnt
        FROM raw_address_record
        WHERE workspace_name = %s
          AND city IS NOT NULL AND city <> ''
          AND province IS NOT NULL AND province <> ''
        GROUP BY city, province
        ORDER BY city ASC, cnt DESC
        """,
        (workspace_name,),
    )
    for row in raw_rows:
        city = normalize_city(row.get("city"))
        province = normalize_space(row.get("province")).upper()
        if city and province and city not in mapping:
            mapping[city] = province
    ref_rows = fetch_all(
        """
        SELECT city, province, COUNT(*) AS cnt
        FROM external_building_reference
        WHERE workspace_name = %s
          AND is_active = 1
          AND city IS NOT NULL AND city <> ''
          AND province IS NOT NULL AND province <> ''
        GROUP BY city, province
        ORDER BY city ASC, cnt DESC
        """,
        (workspace_name,),
    )
    for row in ref_rows:
        city = normalize_city(row.get("city"))
        province = normalize_space(row.get("province")).upper()
        if city and province and city not in mapping:
            mapping[city] = province
    return mapping


def _classify_promotion_row(
    row: dict[str, Any],
    city_province_map: dict[str, str] | None = None,
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    enable_reference_fallback: bool = True,
) -> tuple[dict[str, Any], str | None]:
    enriched = dict(row)
    enriched.update(_extract_structured_fields(enriched, city_province_map))
    if enable_reference_fallback and not _safe_json_loads(enriched.get("reference_json")).get("external_id"):
        fallback_reference = _select_reference_fallback_candidate(workspace_name, enriched)
        if fallback_reference:
            enriched["resolved_reference_external_id"] = fallback_reference.get("external_id")
            enriched["resolved_reference_candidate"] = _json_safe_record(fallback_reference)
            enriched = _apply_reference_fallback_enrichment(enriched, fallback_reference)
    building_key, reference_backed = _canonical_building_key(enriched)
    enriched["building_key"] = building_key
    enriched["reference_backed"] = reference_backed

    if not building_key:
        return enriched, "missing_building_key"
    if not enriched.get("street_number"):
        return enriched, "missing_street_number"
    if not enriched.get("street_name"):
        return enriched, "missing_street_name"
    if not enriched.get("city"):
        return enriched, "missing_city"
    if not enriched.get("province"):
        return enriched, "missing_province"
    return enriched, None


def _extract_structured_fields(
    row: dict[str, Any],
    city_province_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    parser_json = _safe_json_loads(row.get("parser_json"))
    normalize_json = _safe_json_loads(row.get("normalize_json"))
    reference_json = _safe_json_loads(row.get("reference_json"))
    parsed = parser_json.get("best_candidate", {}).get("parsed") or {}
    city = (
        row.get("city")
        or normalize_json.get("city")
        or normalize_json.get("normalized_city")
        or parsed.get("city")
        or reference_json.get("city")
    )
    province = (
        row.get("province")
        or normalize_json.get("province")
        or normalize_json.get("normalized_province")
        or parsed.get("province")
        or reference_json.get("province")
    )
    raw_text = row.get("raw_address_text")
    recovered_city = None
    recovered_province = None
    if (not city or not province) and raw_text:
        recovered_city, recovered_province = _recover_locality_from_raw_text(raw_text)
        city = city or recovered_city
        province = province or recovered_province
    elif raw_text:
        recovered_city, recovered_province = _recover_locality_from_raw_text(raw_text)
    if city and not province and city_province_map:
        province = city_province_map.get(normalize_city(city))
    street_name = _strip_embedded_unit_from_street_name(
        row.get("street_name") or parsed.get("street_name"),
        row.get("suggested_unit_number"),
    )
    return {
        "street_number": row.get("street_number") or parsed.get("street_number"),
        "street_name": street_name,
        "city": city,
        "province": province,
        "raw_tail_city": recovered_city,
        "raw_tail_province": recovered_province,
        "postal_code": (
            row.get("postal_code")
            or normalize_json.get("postal_code")
            or normalize_json.get("normalized_postal_code")
            or parsed.get("postal_code")
            or reference_json.get("postal_code")
        ),
        "latitude": row.get("latitude") if row.get("latitude") is not None else reference_json.get("reference_lat"),
        "longitude": row.get("longitude") if row.get("longitude") is not None else reference_json.get("reference_lon"),
        "country_code": row.get("country_code") or "CA",
    }


def _recover_locality_from_raw_text(raw_address_text: str | None) -> tuple[str | None, str | None]:
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
            or token in _LOCALITY_NOISE_WORDS
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


def _truncate_examples(examples: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    return examples[:limit]


def _json_safe_scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return float(value)
    except Exception:
        return str(value)


def _json_safe_record(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    return {key: _json_safe_scalar(value) for key, value in record.items()}


def _normalize_unit_tokens(unit_value: str | None) -> list[str]:
    text = normalize_space(unit_value).upper()
    if not text:
        return []
    cleaned = re.sub(r"[^A-Z0-9# -]", " ", text)
    return [token for token in cleaned.split() if token]


def _unit_value_needs_normalization(unit_value: str | None) -> bool:
    tokens = _normalize_unit_tokens(unit_value)
    if not tokens:
        return False
    if any(token in _UNIT_NORMALIZATION_NOISE_WORDS for token in tokens):
        return True
    if len(tokens) >= 2 and any(token.isdigit() for token in tokens) and any(token.isalpha() for token in tokens):
        return True
    return False


def _row_has_strong_unit_hint(row: dict[str, Any]) -> bool:
    for value in (
        row.get("raw_address_text"),
        row.get("street_name"),
        row.get("suggested_unit_number"),
    ):
        text = normalize_space(value)
        if text and _STRONG_UNIT_HINT_RE.search(text):
            return True
    return False


def _strip_embedded_unit_from_street_name(
    street_name: str | None,
    suggested_unit_number: str | None,
) -> str | None:
    street_text = normalize_space(street_name).upper()
    normalized_unit = _normalize_canonical_unit_value(suggested_unit_number)
    if not street_text:
        return None
    if not normalized_unit:
        return normalize_street_name(street_text) or street_text
    unit_token = re.escape(normalized_unit)
    patterns = [
        rf"^(.*?)(?:\s+|[\s-]+)(?:UNIT|APT|APARTMENT|SUITE|STE|ROOM|RM|FLOOR|FL)\s*#?\s*{unit_token}$",
        rf"^(.*?)(?:\s+|[\s-]+)#\s*{unit_token}$",
    ]
    for pattern in patterns:
        match = re.match(pattern, street_text, re.IGNORECASE)
        if match:
            stripped = normalize_street_name(match.group(1)) or normalize_space(match.group(1)).upper()
            if stripped:
                return stripped
    return normalize_street_name(street_text) or street_text


def _classify_unit_convergence_quality(row_details: list[dict[str, Any]]) -> tuple[str, dict[str, int]]:
    counts = {
        "normalizable_unit_values": 0,
        "single_unit_rows": 0,
        "commercial_rows": 0,
        "single_unit_rows_with_unit_hint": 0,
        "rows_with_unit_signal": 0,
    }
    for row in row_details:
        if _unit_value_needs_normalization(row.get("suggested_unit_number")):
            counts["normalizable_unit_values"] += 1
        if _normalize_canonical_unit_value(row.get("suggested_unit_number")) or _row_has_strong_unit_hint(row):
            counts["rows_with_unit_signal"] += 1
        if row.get("building_type") == "single_unit":
            counts["single_unit_rows"] += 1
            if _row_has_strong_unit_hint(row):
                counts["single_unit_rows_with_unit_hint"] += 1
        if row.get("building_type") == "commercial":
            counts["commercial_rows"] += 1
    if counts["normalizable_unit_values"] > 0:
        return "unit_normalization_review", counts
    if (
        len(row_details) >= 5
        and counts["rows_with_unit_signal"] >= len(row_details) - 1
        and counts["single_unit_rows"] <= 1
        and counts["commercial_rows"] <= 1
        and (counts["single_unit_rows"] + counts["commercial_rows"]) > 0
    ):
        return "benign_multi_unit_convergence", counts
    if (
        counts["single_unit_rows"] > 0
        and counts["single_unit_rows"] == counts["single_unit_rows_with_unit_hint"]
        and counts["single_unit_rows"] < len(row_details)
    ):
        return "benign_multi_unit_convergence", counts
    if counts["single_unit_rows"] > 0:
        return "mixed_building_type_review", counts
    if counts["commercial_rows"] == len(row_details) and row_details:
        return "commercial_unit_convergence", counts
    return "benign_multi_unit_convergence", counts


def _resolve_canonical_building_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "street_number": row.get("street_number"),
        "street_name": row.get("street_name"),
        "city": row.get("city"),
        "province": row.get("province"),
        "postal_code": row.get("postal_code"),
        "country_code": row.get("country_code"),
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
    }
    if row.get("reference_backed"):
        candidate = row.get("resolved_reference_candidate") or {}
        candidate_street = normalize_street_name(candidate.get("street_name")) or candidate.get("street_name")
        candidate_city = normalize_city(
            candidate.get("city")
            or candidate.get("municipality")
            or candidate.get("county")
        )
        candidate_province = normalize_space(candidate.get("province")).upper() or payload["province"]
        if candidate_street:
            payload["street_name"] = candidate_street
        if candidate_city:
            payload["city"] = candidate_city
        if candidate_province:
            payload["province"] = candidate_province
    return payload


def _fetch_hotspot_row_details(workspace_name: str, raw_ids: list[int]) -> list[dict[str, Any]]:
    if not raw_ids:
        return []
    placeholders = ",".join(["%s"] * len(raw_ids))
    query = f"""
        SELECT
            acr.raw_id,
            acr.raw_address_text,
            acr.building_type,
            acr.suggested_unit_number,
            acr.confidence,
            acr.base_address_key,
            acr.normalize_json,
            acr.reference_json,
            acr.parser_json,
            r.country_code
        FROM address_cleaning_result acr
        JOIN raw_address_record r ON acr.raw_id = r.raw_id
        WHERE acr.workspace_name = %s
          AND acr.raw_id IN ({placeholders})
        ORDER BY acr.raw_id ASC
    """
    params: tuple[Any, ...] = (workspace_name, *raw_ids)
    rows = fetch_all(query, params)
    details: list[dict[str, Any]] = []
    for row in rows:
        structured = _extract_structured_fields(row)
        recovered_city, recovered_province = _recover_locality_from_raw_text(row.get("raw_address_text"))
        details.append(
            {
                "raw_id": row.get("raw_id"),
                "raw_address_text": row.get("raw_address_text"),
                "street_number": structured.get("street_number"),
                "street_name": structured.get("street_name"),
                "city": structured.get("city"),
                "province": structured.get("province"),
                "raw_tail_city": recovered_city,
                "raw_tail_province": recovered_province,
                "building_type": row.get("building_type"),
                "suggested_unit_number": row.get("suggested_unit_number"),
                "confidence": _json_safe_scalar(row.get("confidence")),
            }
        )
    return details


def _attach_hotspot_details(
    workspace_name: str,
    hotspots: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, Any]]:
    detailed: list[dict[str, Any]] = []
    for hotspot in hotspots[:limit]:
        item = dict(hotspot)
        item["row_details"] = _fetch_hotspot_row_details(workspace_name, list(hotspot.get("raw_ids") or []))
        item["canonical_building_detail"] = _fetch_canonical_building_detail(
            workspace_name,
            str(hotspot.get("building_key") or ""),
        )
        if "unit_key_count" in hotspot:
            item["canonical_unit_values"] = _fetch_canonical_unit_values(
                workspace_name,
                str(hotspot.get("building_key") or ""),
            )
            unit_quality, unit_quality_counts = _classify_unit_convergence_quality(item["row_details"])
            if item["canonical_unit_values"] and all(
                not _unit_value_needs_normalization(value) for value in item["canonical_unit_values"]
            ):
                if unit_quality == "unit_normalization_review":
                    unit_quality = "benign_multi_unit_convergence"
            item["unit_convergence_quality"] = unit_quality
            item["unit_convergence_quality_counts"] = unit_quality_counts
        detailed.append(item)
    return detailed


def _fetch_canonical_building_detail(
    workspace_name: str,
    building_key: str,
) -> dict[str, Any] | None:
    if not building_key:
        return None
    rows = fetch_all(
        """
        SELECT building_key, street_number, street_name, city, province, postal_code, country_code
        FROM canonical_building
        WHERE workspace_name = %s AND building_key = %s
        LIMIT 1
        """,
        (workspace_name, building_key),
    )
    return _json_safe_record(rows[0]) if rows else None


def _fetch_canonical_unit_values(
    workspace_name: str,
    building_key: str,
) -> list[str]:
    if not building_key:
        return []
    rows = fetch_all(
        """
        SELECT unit_number
        FROM canonical_unit
        WHERE workspace_name = %s AND building_key = %s
        ORDER BY unit_number ASC
        """,
        (workspace_name, building_key),
    )
    return [str(row.get("unit_number")) for row in rows if row.get("unit_number")]


def _city_compatible(left: str | None, right: str | None) -> bool:
    left = normalize_city(left) or ""
    right = normalize_city(right) or ""
    if not left or not right:
        return True
    if left == right:
        return True
    left_tokens = {token for token in left.upper().split() if token}
    right_tokens = {token for token in right.upper().split() if token}
    if not left_tokens or not right_tokens:
        return True
    overlap = left_tokens & right_tokens
    return bool(overlap) and (len(overlap) / min(len(left_tokens), len(right_tokens))) >= 0.5


def _normalized_street_tokens(value: str | None) -> set[str]:
    street_name = normalize_street_name(value) or normalize_space(value).upper()
    tokens: set[str] = set()
    for token in street_name.split():
        if not token:
            continue
        tokens.add(_STREET_SUFFIX_NORMALIZATION.get(token, token))
    return tokens


def _street_equivalent(left: str | None, right: str | None) -> bool:
    left_tokens = _normalized_street_tokens(left)
    right_tokens = _normalized_street_tokens(right)
    return bool(left_tokens) and left_tokens == right_tokens


def _street_token_overlap(left: str | None, right: str | None) -> float:
    left_tokens = _normalized_street_tokens(left)
    right_tokens = _normalized_street_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = left_tokens & right_tokens
    return len(overlap) / min(len(left_tokens), len(right_tokens))


def _fetch_reference_candidates(
    workspace_name: str,
    street_number: str | None,
    province: str | None,
) -> list[dict[str, Any]]:
    if not street_number or not province:
        return []
    return fetch_all(
        """
        SELECT
            external_id,
            street_number,
            street_name,
            unit_number,
            city,
            municipality,
            county,
            province,
            quality_score,
            reference_tier
        FROM external_building_reference
        WHERE workspace_name = %s
          AND is_active = 1
          AND street_number = %s
          AND province = %s
        ORDER BY quality_score DESC, external_id ASC
        LIMIT 20
        """,
        (workspace_name, street_number, province),
    )


def _select_reference_fallback_candidate(
    workspace_name: str,
    detail: dict[str, Any],
) -> dict[str, Any] | None:
    reference_candidates = _fetch_reference_candidates(
        workspace_name,
        str(detail.get("street_number") or "").strip(),
        str(detail.get("province") or "").strip().upper(),
    )
    if not reference_candidates:
        return None
    street_name = detail.get("street_name")
    city = detail.get("city")
    raw_tail_city = detail.get("raw_tail_city")
    raw_address_text = normalize_space(detail.get("raw_address_text")).upper()
    best_candidate: dict[str, Any] | None = None
    best_score = 0.0
    for candidate in reference_candidates:
        candidate_city = candidate.get("city") or candidate.get("municipality") or candidate.get("county")
        candidate_city_norm = normalize_city(candidate_city) or ""
        street_overlap = _street_token_overlap(street_name, candidate.get("street_name"))
        locality_match = _city_compatible(city, candidate_city) or _city_compatible(raw_tail_city, candidate_city)
        city_embedded_in_street = bool(candidate_city_norm) and candidate_city_norm.upper() in (normalize_space(street_name).upper())
        city_embedded_in_raw = bool(candidate_city_norm) and candidate_city_norm.upper() in raw_address_text
        score = (
            0.6 * street_overlap
            + (0.2 if locality_match else 0.0)
            + (0.15 if city_embedded_in_street else 0.0)
            + (0.05 if city_embedded_in_raw else 0.0)
        )
        if score > best_score:
            best_score = score
            best_candidate = dict(candidate)
    if best_candidate is None:
        return None
    if best_score < 0.75:
        return None
    if _street_token_overlap(street_name, best_candidate.get("street_name")) < 0.6:
        return None
    return best_candidate


def _apply_reference_fallback_enrichment(
    detail: dict[str, Any],
    reference_candidate: dict[str, Any],
) -> dict[str, Any]:
    enriched = dict(detail)
    candidate_street = normalize_street_name(reference_candidate.get("street_name")) or reference_candidate.get("street_name")
    candidate_city = normalize_city(
        reference_candidate.get("city")
        or reference_candidate.get("municipality")
        or reference_candidate.get("county")
    )
    candidate_province = normalize_space(reference_candidate.get("province")).upper() or detail.get("province")
    if _street_token_overlap(detail.get("street_name"), candidate_street) >= 0.6:
        enriched["street_name"] = candidate_street
    current_city = detail.get("city")
    raw_tail_city = detail.get("raw_tail_city")
    if candidate_city:
        if _city_compatible(raw_tail_city, candidate_city):
            enriched["city"] = candidate_city
        elif not _city_compatible(current_city, candidate_city):
            enriched["city"] = candidate_city
    if candidate_province:
        enriched["province"] = candidate_province
    return enriched


def _classify_reference_gap_reason(
    detail: dict[str, Any],
    reference_candidates: list[dict[str, Any]],
) -> tuple[str, dict[str, Any] | None]:
    if not reference_candidates:
        return "no_reference_candidate_found", None
    street_name = detail.get("street_name")
    city = detail.get("city")
    exact_street_candidates: list[dict[str, Any]] = []
    locality_mismatch_candidates: list[dict[str, Any]] = []
    street_tail_mismatch_candidates: list[dict[str, Any]] = []
    for candidate in reference_candidates:
        candidate_street = candidate.get("street_name")
        candidate_city = candidate.get("city") or candidate.get("municipality") or candidate.get("county")
        if _street_equivalent(street_name, candidate_street):
            exact_street_candidates.append(candidate)
            if not _city_compatible(city, candidate_city):
                locality_mismatch_candidates.append(candidate)
            continue
        if _street_token_overlap(street_name, candidate_street) >= 0.6:
            street_tail_mismatch_candidates.append(candidate)
    if locality_mismatch_candidates:
        return "reference_candidate_found_but_locality_mismatch", locality_mismatch_candidates[0]
    if street_tail_mismatch_candidates:
        return "reference_candidate_found_but_street_tail_mismatch", street_tail_mismatch_candidates[0]
    if exact_street_candidates:
        return "reference_candidate_found_but_matcher_threshold", exact_street_candidates[0]
    best_overlap_candidate = None
    best_overlap = 0.0
    for candidate in reference_candidates:
        overlap = _street_token_overlap(street_name, candidate.get("street_name"))
        if overlap > best_overlap:
            best_overlap = overlap
            best_overlap_candidate = candidate
    if best_overlap < 0.25:
        return "no_reference_candidate_found", None
    if best_overlap_candidate is not None:
        return "reference_candidate_found_but_street_conflict", best_overlap_candidate
    return "reference_candidate_found_but_street_conflict", reference_candidates[0]


def _derive_reference_gap_diagnostics(
    workspace_name: str,
    hotspot_details: list[dict[str, Any]],
) -> dict[str, Any]:
    reason_counts = {
        "no_reference_candidate_found": 0,
        "reference_candidate_found_but_locality_mismatch": 0,
        "reference_candidate_found_but_street_tail_mismatch": 0,
        "reference_candidate_found_but_matcher_threshold": 0,
        "reference_candidate_found_but_street_conflict": 0,
    }
    hotspot_details_with_reasons: list[dict[str, Any]] = []
    for hotspot in hotspot_details:
        if hotspot.get("hotspot_risk") == "low_risk_repeat":
            continue
        item = dict(hotspot)
        row_reason_counts: dict[str, int] = {}
        row_examples: list[dict[str, Any]] = []
        for row in hotspot.get("row_details") or []:
            candidates = _fetch_reference_candidates(
                workspace_name,
                str(row.get("street_number") or "").strip(),
                str(row.get("province") or "").strip().upper(),
            )
            reason, candidate = _classify_reference_gap_reason(row, candidates)
            reason_counts[reason] += 1
            row_reason_counts[reason] = row_reason_counts.get(reason, 0) + 1
            row_examples.append(
                {
                    "raw_id": row.get("raw_id"),
                    "raw_address_text": row.get("raw_address_text"),
                    "street_number": row.get("street_number"),
                    "street_name": row.get("street_name"),
                    "city": row.get("city"),
                    "province": row.get("province"),
                    "raw_tail_city": row.get("raw_tail_city"),
                    "raw_tail_province": row.get("raw_tail_province"),
                    "diagnostic_reason": reason,
                    "recommended_action": _reference_gap_action_hint(reason),
                    "reference_candidate": _json_safe_record(candidate),
                }
            )
        dominant_reason = max(row_reason_counts.items(), key=lambda item: item[1])[0] if row_reason_counts else "no_reference_candidate_found"
        item["reference_gap_reason"] = dominant_reason
        item["reference_gap_action"] = _reference_gap_action_hint(dominant_reason)
        item["reference_gap_reason_counts"] = row_reason_counts
        item["reference_gap_row_examples"] = row_examples[:5]
        hotspot_details_with_reasons.append(item)
    return {
        "reference_gap_reason_summary": reason_counts,
        "reference_gap_hotspot_details": hotspot_details_with_reasons,
    }


def _derive_residual_hotspot_risk_summary(diagnostics: dict[str, Any]) -> dict[str, int]:
    summary = {
        "likely_multi_unit_convergence": 0,
        "likely_reference_gap": 0,
        "likely_merge_review": 0,
        "low_risk_repeat": 0,
        "benign": 0,
    }
    for item in diagnostics.get("unit_convergence_hotspot_details") or []:
        quality = item.get("unit_convergence_quality")
        if quality in {"benign_multi_unit_convergence", "commercial_unit_convergence"}:
            summary["likely_multi_unit_convergence"] += 1
        elif quality in {"unit_normalization_review", "mixed_building_type_review"}:
            summary["likely_merge_review"] += 1
    for item in diagnostics.get("reference_gap_hotspot_details") or []:
        risk = item.get("hotspot_risk")
        reason = item.get("reference_gap_reason")
        if risk == "low_risk_repeat":
            summary["low_risk_repeat"] += 1
            continue
        if reason in {
            "no_reference_candidate_found",
            "reference_candidate_found_but_locality_mismatch",
            "reference_candidate_found_but_street_tail_mismatch",
        }:
            summary["likely_reference_gap"] += 1
        elif reason in {
            "reference_candidate_found_but_street_conflict",
            "reference_candidate_found_but_matcher_threshold",
        }:
            summary["likely_merge_review"] += 1
    return summary


def _reference_gap_action_hint(reason: str) -> str:
    mapping = {
        "no_reference_candidate_found": "expand_reference_coverage",
        "reference_candidate_found_but_locality_mismatch": "review_locality_normalization_and_city_mapping",
        "reference_candidate_found_but_street_tail_mismatch": "review_street_tail_split_and_reference_fusion",
        "reference_candidate_found_but_matcher_threshold": "review_reference_match_threshold_or_candidate_scoring",
        "reference_candidate_found_but_street_conflict": "review_parser_street_extraction_and_base_key_quality",
    }
    return mapping.get(reason, "review_reference_gap")


def _classify_hotspot_risk(
    raw_id_count: int,
    unit_key_count: int,
    reference_backed: bool,
    homogeneous_repeat: bool = False,
    single_unit_only: bool = False,
) -> str:
    if unit_key_count >= 3:
        return "likely_multi_unit_convergence"
    if homogeneous_repeat and unit_key_count == 0:
        return "low_risk_repeat"
    if homogeneous_repeat and reference_backed and unit_key_count <= 1:
        return "low_risk_repeat"
    if single_unit_only and unit_key_count == 0 and raw_id_count >= 2:
        return "low_risk_repeat"
    if reference_backed and unit_key_count == 1 and raw_id_count >= 2:
        return "low_risk_repeat"
    if raw_id_count >= 4 and not reference_backed:
        return "likely_reference_gap"
    if raw_id_count >= 4 and reference_backed:
        return "likely_merge_review"
    if raw_id_count >= 2:
        return "low_risk_repeat"
    return "benign"


def _derive_asset_quality_diagnostics(
    rows: list[dict[str, Any]],
    canonical_building_count: int,
    canonical_unit_count: int,
    confidence_threshold: float,
    city_province_map: dict[str, str] | None = None,
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    enable_reference_fallback: bool = False,
) -> dict[str, Any]:
    eligible_rows = 0
    eligible_reference_rows = 0
    eligible_non_reference_rows = 0
    eligible_rows_with_units = 0
    eligible_multi_unit_rows = 0
    eligible_multi_unit_without_unit_rows = 0
    reference_backed_unit_rows = 0

    unique_building_keys: set[str] = set()
    unique_reference_building_keys: set[str] = set()
    unique_base_building_keys: set[str] = set()
    unique_unit_keys: set[str] = set()
    unique_reference_unit_keys: set[str] = set()
    building_key_to_raw_ids: dict[str, list[int]] = {}
    reference_backed_building_key_to_raw_ids: dict[str, list[int]] = {}
    non_reference_building_key_to_raw_ids: dict[str, list[int]] = {}
    building_key_to_unit_keys: dict[str, set[str]] = {}
    building_key_to_row_signatures: dict[str, set[tuple[str, str, str, str, str, str]]] = {}
    building_key_to_building_types: dict[str, set[str]] = {}
    skipped_reason_counts = {
        "missing_building_key": 0,
        "missing_street_number": 0,
        "missing_street_name": 0,
        "missing_city": 0,
        "missing_province": 0,
    }

    no_reference_examples: list[dict[str, Any]] = []
    multi_unit_without_unit_examples: list[dict[str, Any]] = []
    duplicate_hotspot_examples: list[dict[str, Any]] = []
    reference_backed_hotspot_examples: list[dict[str, Any]] = []
    non_reference_hotspot_examples: list[dict[str, Any]] = []
    unit_convergence_hotspot_examples: list[dict[str, Any]] = []
    hotspot_risk_summary = {
        "likely_multi_unit_convergence": 0,
        "likely_reference_gap": 0,
        "likely_merge_review": 0,
        "low_risk_repeat": 0,
        "benign": 0,
    }
    skipped_examples: dict[str, list[dict[str, Any]]] = {key: [] for key in skipped_reason_counts}

    for row in rows:
        row, skip_reason = _classify_promotion_row(
            row,
            city_province_map,
            workspace_name,
            enable_reference_fallback=enable_reference_fallback,
        )
        eligible_rows += 1
        if skip_reason:
            skipped_reason_counts[skip_reason] += 1
            skipped_examples[skip_reason].append(
                {
                    "raw_id": row.get("raw_id"),
                    "raw_address_text": row.get("raw_address_text"),
                    "street_number": row.get("street_number"),
                    "street_name": row.get("street_name"),
                    "city": row.get("city"),
                    "province": row.get("province"),
                    "building_type": row.get("building_type"),
                    "confidence": _json_safe_scalar(row.get("confidence")),
                }
            )
            continue
        building_key = str(row["building_key"])
        reference_backed = bool(row["reference_backed"])
        unique_building_keys.add(building_key)
        building_key_to_raw_ids.setdefault(building_key, []).append(int(row.get("raw_id") or 0))
        building_key_to_unit_keys.setdefault(building_key, set())
        building_key_to_row_signatures.setdefault(building_key, set()).add(
            (
                normalize_space(row.get("raw_address_text")).upper(),
                normalize_space(row.get("street_number")).upper(),
                normalize_space(row.get("street_name")).upper(),
                normalize_space(row.get("city")).upper(),
                normalize_space(row.get("province")).upper(),
                normalize_space(row.get("suggested_unit_number")).upper(),
            )
        )
        building_key_to_building_types.setdefault(building_key, set()).add(str(row.get("building_type") or ""))

        if reference_backed:
            eligible_reference_rows += 1
            unique_reference_building_keys.add(building_key)
            reference_backed_building_key_to_raw_ids.setdefault(building_key, []).append(int(row.get("raw_id") or 0))
        else:
            eligible_non_reference_rows += 1
            unique_base_building_keys.add(building_key)
            non_reference_building_key_to_raw_ids.setdefault(building_key, []).append(int(row.get("raw_id") or 0))

        unit_number = row.get("suggested_unit_number")
        unit_key = _canonical_unit_key(building_key, unit_number)
        if unit_key:
            eligible_rows_with_units += 1
            unique_unit_keys.add(unit_key)
            building_key_to_unit_keys[building_key].add(unit_key)
            if reference_backed:
                reference_backed_unit_rows += 1
                unique_reference_unit_keys.add(unit_key)

        building_type = str(row.get("building_type") or "")
        if building_type == "multi_unit":
            eligible_multi_unit_rows += 1
            if not unit_key:
                eligible_multi_unit_without_unit_rows += 1
                multi_unit_without_unit_examples.append(
                    {
                        "raw_id": row.get("raw_id"),
                        "raw_address_text": row.get("raw_address_text"),
                        "street_number": row.get("street_number"),
                        "street_name": row.get("street_name"),
                        "confidence": _json_safe_scalar(row.get("confidence")),
                    }
                )

        if not reference_backed:
            no_reference_examples.append(
                {
                    "raw_id": row.get("raw_id"),
                    "raw_address_text": row.get("raw_address_text"),
                    "street_number": row.get("street_number"),
                    "street_name": row.get("street_name"),
                    "building_type": row.get("building_type"),
                    "confidence": _json_safe_scalar(row.get("confidence")),
                }
            )

    for building_key, raw_ids in sorted(building_key_to_raw_ids.items(), key=lambda item: len(item[1]), reverse=True):
        if len(raw_ids) <= 1:
            break
        unit_key_count = len(building_key_to_unit_keys.get(building_key, set()))
        reference_backed = building_key in unique_reference_building_keys
        hotspot_risk = _classify_hotspot_risk(
            len(raw_ids),
            unit_key_count,
            reference_backed,
            homogeneous_repeat=len(building_key_to_row_signatures.get(building_key, set())) == 1,
            single_unit_only=building_key_to_building_types.get(building_key, set()) == {"single_unit"},
        )
        hotspot_risk_summary[hotspot_risk] += 1
        duplicate_hotspot_examples.append(
            {
                "building_key": building_key,
                "raw_id_count": len(raw_ids),
                "raw_ids": raw_ids[:10],
                "unit_key_count": unit_key_count,
                "reference_backed": reference_backed,
                "hotspot_risk": hotspot_risk,
            }
        )
    for building_key, raw_ids in sorted(reference_backed_building_key_to_raw_ids.items(), key=lambda item: len(item[1]), reverse=True):
        if len(raw_ids) <= 1:
            break
        unit_key_count = len(building_key_to_unit_keys.get(building_key, set()))
        reference_backed_hotspot_examples.append(
            {
                "building_key": building_key,
                "raw_id_count": len(raw_ids),
                "raw_ids": raw_ids[:10],
                "unit_key_count": unit_key_count,
                "hotspot_risk": _classify_hotspot_risk(
                    len(raw_ids),
                    unit_key_count,
                    True,
                    homogeneous_repeat=len(building_key_to_row_signatures.get(building_key, set())) == 1,
                    single_unit_only=building_key_to_building_types.get(building_key, set()) == {"single_unit"},
                ),
            }
        )
    for building_key, raw_ids in sorted(non_reference_building_key_to_raw_ids.items(), key=lambda item: len(item[1]), reverse=True):
        if len(raw_ids) <= 1:
            break
        unit_key_count = len(building_key_to_unit_keys.get(building_key, set()))
        non_reference_hotspot_examples.append(
            {
                "building_key": building_key,
                "raw_id_count": len(raw_ids),
                "raw_ids": raw_ids[:10],
                "unit_key_count": unit_key_count,
                "hotspot_risk": _classify_hotspot_risk(
                    len(raw_ids),
                    unit_key_count,
                    False,
                    homogeneous_repeat=len(building_key_to_row_signatures.get(building_key, set())) == 1,
                    single_unit_only=building_key_to_building_types.get(building_key, set()) == {"single_unit"},
                ),
            }
        )
    for building_key, unit_keys in sorted(building_key_to_unit_keys.items(), key=lambda item: len(item[1]), reverse=True):
        if len(unit_keys) <= 1:
            continue
        unit_convergence_hotspot_examples.append(
            {
                "building_key": building_key,
                "unit_key_count": len(unit_keys),
                "unit_keys": sorted(unit_keys)[:10],
                "raw_id_count": len(building_key_to_raw_ids.get(building_key, [])),
                "raw_ids": building_key_to_raw_ids.get(building_key, [])[:10],
            }
        )

    unique_building_count = len(unique_building_keys)
    unique_unit_count = len(unique_unit_keys)
    multi_unit_unit_coverage = (
        round((eligible_multi_unit_rows - eligible_multi_unit_without_unit_rows) / eligible_multi_unit_rows, 4)
        if eligible_multi_unit_rows
        else 1.0
    )

    return {
        "confidence_threshold": confidence_threshold,
        "eligible_rows": eligible_rows,
        "eligible_reference_rows": eligible_reference_rows,
        "eligible_non_reference_rows": eligible_non_reference_rows,
        "eligible_rows_with_units": eligible_rows_with_units,
        "eligible_multi_unit_rows": eligible_multi_unit_rows,
        "eligible_multi_unit_without_unit_rows": eligible_multi_unit_without_unit_rows,
        "unique_building_keys_total": unique_building_count,
        "unique_reference_backed_building_keys": len(unique_reference_building_keys),
        "unique_basekey_building_keys": len(unique_base_building_keys),
        "unique_unit_keys_total": unique_unit_count,
        "unique_reference_backed_unit_keys": len(unique_reference_unit_keys),
        "reference_backed_row_ratio": round(eligible_reference_rows / eligible_rows, 4) if eligible_rows else 0.0,
        "reference_backed_building_ratio": round(len(unique_reference_building_keys) / unique_building_count, 4) if unique_building_count else 0.0,
        "reference_backed_unit_ratio": round(reference_backed_unit_rows / eligible_rows_with_units, 4) if eligible_rows_with_units else 0.0,
        "multi_unit_unit_coverage": multi_unit_unit_coverage,
        "avg_rows_per_building_key": round(eligible_rows / unique_building_count, 4) if unique_building_count else 0.0,
        "avg_rows_per_unit_key": round(eligible_rows_with_units / unique_unit_count, 4) if unique_unit_count else 0.0,
        "canonical_building_count": canonical_building_count,
        "canonical_unit_count": canonical_unit_count,
        "canonical_building_gap": max(unique_building_count - canonical_building_count, 0),
        "canonical_unit_gap": max(unique_unit_count - canonical_unit_count, 0),
        "promotion_skip_reason_counts": skipped_reason_counts,
        "no_reference_examples": _truncate_examples(no_reference_examples),
        "multi_unit_without_unit_examples": _truncate_examples(multi_unit_without_unit_examples),
        "duplicate_building_key_hotspots": _truncate_examples(duplicate_hotspot_examples),
        "reference_backed_building_hotspots": _truncate_examples(reference_backed_hotspot_examples),
        "non_reference_building_hotspots": _truncate_examples(non_reference_hotspot_examples),
        "unit_convergence_hotspots": _truncate_examples(unit_convergence_hotspot_examples),
        "hotspot_risk_summary": hotspot_risk_summary,
        "skipped_examples": {key: _truncate_examples(value) for key, value in skipped_examples.items()},
    }


def generate_asset_quality_report(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    confidence_threshold: float = 0.85,
) -> dict[str, Any]:
    query = """
        SELECT
            acr.raw_id,
            acr.base_address_key,
            acr.suggested_unit_number,
            acr.building_type,
            acr.decision,
            acr.confidence,
            acr.normalize_json,
            acr.reference_json,
            acr.parser_json,
            acr.raw_address_text,
            r.country_code
        FROM address_cleaning_result acr
        JOIN raw_address_record r ON acr.raw_id = r.raw_id
        WHERE acr.workspace_name = %s
          AND acr.decision = 'accept'
          AND acr.confidence >= %s
          AND acr.checkpoint_status = 'completed'
    """
    rows = fetch_all(query, (workspace_name, confidence_threshold))
    stats = get_asset_stats(workspace_name)
    city_province_map = _load_city_to_province_map(workspace_name)
    diagnostics = _derive_asset_quality_diagnostics(
        rows,
        canonical_building_count=int(stats.get("total_buildings") or 0),
        canonical_unit_count=int(stats.get("total_units") or 0),
        confidence_threshold=confidence_threshold,
        city_province_map=city_province_map,
        workspace_name=workspace_name,
        enable_reference_fallback=True,
    )
    diagnostics["reference_backed_building_hotspot_details"] = _attach_hotspot_details(
        workspace_name, diagnostics["reference_backed_building_hotspots"]
    )
    diagnostics["non_reference_building_hotspot_details"] = _attach_hotspot_details(
        workspace_name, diagnostics["non_reference_building_hotspots"]
    )
    diagnostics.update(
        _derive_reference_gap_diagnostics(
            workspace_name,
            diagnostics["non_reference_building_hotspot_details"],
        )
    )
    diagnostics["unit_convergence_hotspot_details"] = _attach_hotspot_details(
        workspace_name, diagnostics["unit_convergence_hotspots"]
    )
    unit_convergence_quality_summary = {
        "benign_multi_unit_convergence": 0,
        "unit_normalization_review": 0,
        "mixed_building_type_review": 0,
        "commercial_unit_convergence": 0,
    }
    for item in diagnostics["unit_convergence_hotspot_details"]:
        quality = item.get("unit_convergence_quality")
        if quality in unit_convergence_quality_summary:
            unit_convergence_quality_summary[quality] += 1
    diagnostics["unit_convergence_quality_summary"] = unit_convergence_quality_summary
    diagnostics["residual_hotspot_risk_summary"] = _derive_residual_hotspot_risk_summary(diagnostics)

    report_dir = Path("runtime/reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"{workspace_name}_asset_quality_report_{timestamp}.md"
    latest_path = report_dir / f"{workspace_name}_asset_quality_report_latest.md"

    lines = [
        f"# Asset Quality Report ({workspace_name})",
        "",
        f"- Generated At: {datetime.now().isoformat(timespec='seconds')}",
        f"- Confidence Threshold: {confidence_threshold}",
        "",
        "## Coverage",
        f"- Eligible Accepted Rows: {diagnostics['eligible_rows']}",
        f"- Eligible Reference-Backed Rows: {diagnostics['eligible_reference_rows']}",
        f"- Eligible Non-Reference Rows: {diagnostics['eligible_non_reference_rows']}",
        f"- Eligible Rows With Units: {diagnostics['eligible_rows_with_units']}",
        f"- Eligible Multi-Unit Rows: {diagnostics['eligible_multi_unit_rows']}",
        f"- Eligible Multi-Unit Rows Without Unit: {diagnostics['eligible_multi_unit_without_unit_rows']}",
        "",
        "## Canonical Convergence",
        f"- Unique Building Keys: {diagnostics['unique_building_keys_total']}",
        f"- Unique Reference-Backed Building Keys: {diagnostics['unique_reference_backed_building_keys']}",
        f"- Unique Base-Key Building Keys: {diagnostics['unique_basekey_building_keys']}",
        f"- Unique Unit Keys: {diagnostics['unique_unit_keys_total']}",
        f"- Unique Reference-Backed Unit Keys: {diagnostics['unique_reference_backed_unit_keys']}",
        f"- Avg Rows Per Building Key: {diagnostics['avg_rows_per_building_key']}",
        f"- Avg Rows Per Unit Key: {diagnostics['avg_rows_per_unit_key']}",
        "",
        "## Ratios",
        f"- Reference-Backed Row Ratio: {diagnostics['reference_backed_row_ratio']}",
        f"- Reference-Backed Building Ratio: {diagnostics['reference_backed_building_ratio']}",
        f"- Reference-Backed Unit Ratio: {diagnostics['reference_backed_unit_ratio']}",
        f"- Multi-Unit Unit Coverage: {diagnostics['multi_unit_unit_coverage']}",
        "",
        "## Canonical Tables",
        f"- Canonical Buildings: {diagnostics['canonical_building_count']}",
        f"- Canonical Units: {diagnostics['canonical_unit_count']}",
        f"- Canonical Building Gap: {diagnostics['canonical_building_gap']}",
        f"- Canonical Unit Gap: {diagnostics['canonical_unit_gap']}",
        "",
        "## Promotion Skip Reasons",
        dumps_payload(diagnostics["promotion_skip_reason_counts"]),
        "",
        "## High-Risk Examples",
        "### Accepted Rows Without Reference",
        dumps_payload(diagnostics["no_reference_examples"]),
        "",
        "### Multi-Unit Rows Without Unit",
        dumps_payload(diagnostics["multi_unit_without_unit_examples"]),
        "",
        "### Duplicate Building-Key Hotspots",
        dumps_payload(diagnostics["duplicate_building_key_hotspots"]),
        "",
        "### Hotspot Risk Summary",
        dumps_payload(diagnostics["hotspot_risk_summary"]),
        "",
        "### Residual Hotspot Risk Summary",
        dumps_payload(diagnostics["residual_hotspot_risk_summary"]),
        "",
        "### Reference-Backed Building Hotspots",
        dumps_payload(diagnostics["reference_backed_building_hotspots"]),
        "",
        "### Reference-Backed Building Hotspot Details",
        dumps_payload(diagnostics["reference_backed_building_hotspot_details"]),
        "",
        "### Non-Reference Building Hotspots",
        dumps_payload(diagnostics["non_reference_building_hotspots"]),
        "",
        "### Non-Reference Building Hotspot Details",
        dumps_payload(diagnostics["non_reference_building_hotspot_details"]),
        "",
        "### Reference Gap Reason Summary",
        dumps_payload(diagnostics["reference_gap_reason_summary"]),
        "",
        "### Reference Gap Hotspot Details",
        dumps_payload(diagnostics["reference_gap_hotspot_details"]),
        "",
        "### Unit Convergence Hotspots",
        dumps_payload(diagnostics["unit_convergence_hotspots"]),
        "",
        "### Unit Convergence Quality Summary",
        dumps_payload(diagnostics["unit_convergence_quality_summary"]),
        "",
        "### Unit Convergence Hotspot Details",
        dumps_payload(diagnostics["unit_convergence_hotspot_details"]),
        "",
        "### Skipped Examples",
        dumps_payload(diagnostics["skipped_examples"]),
        "",
    ]
    report_content = "\n".join(lines)
    report_path.write_text(report_content, encoding="utf-8")
    latest_path.write_text(report_content, encoding="utf-8")

    return {
        "workspace_name": workspace_name,
        "report_path": str(report_path),
        "latest_report_path": str(latest_path),
        "diagnostics": diagnostics,
    }

def promote_results_to_assets(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME) -> dict[str, Any]:
    """
    Orchestrates large-scale promotion with Reference-first merging.
    编排采用参考库优先合并策略的大规模提升任务。
    """
    logger.info("Consolidated asset promotion started (Ref-first): %s", workspace_name)
    
    # 1. Fetch high-confidence candidates including reference metadata
    # 1. 获取包含参考元数据的高置信度候选样本
    query = """
        SELECT acr.*, r.city, r.province, r.postal_code, r.country_code, 
               r.latitude, r.longitude, acr.reference_json
        FROM address_cleaning_result acr
        JOIN raw_address_record r ON acr.raw_id = r.raw_id
        WHERE acr.workspace_name = %s 
          AND acr.decision = 'accept'
          AND acr.confidence >= 0.85
          AND acr.checkpoint_status = 'completed'
    """
    results = fetch_all(query, (workspace_name,))
    city_province_map = _load_city_to_province_map(workspace_name)
    
    if not results:
        return {
            "status": "success",
            "new_buildings": 0,
            "new_units": 0,
            "promoted_buildings": 0,
            "promoted_units": 0,
            "total_processed": 0,
            "reference_backed_rows_processed": 0,
            "non_reference_rows_processed": 0,
            "rows_with_units_processed": 0,
            "unique_building_keys_processed": 0,
            "unique_unit_keys_processed": 0,
        }

    buildings_added = 0
    units_added = 0
    reference_backed_rows_processed = 0
    non_reference_rows_processed = 0
    rows_with_units_processed = 0
    unique_building_keys_processed: set[str] = set()
    unique_unit_keys_processed: set[str] = set()

    with db_cursor() as (conn, cursor):
        for row in results:
            row, skip_reason = _classify_promotion_row(row, city_province_map, workspace_name)
            building_key = row.get("building_key")
            building_payload = _resolve_canonical_building_payload(row)
            if row.get("reference_backed"):
                reference_backed_rows_processed += 1
            else:
                non_reference_rows_processed += 1
            if skip_reason:
                continue
            unique_building_keys_processed.add(building_key)

            # 2. Upsert Building with exact key deduplication
            # 2. 通过精确键去重进行建筑更新/插入
            cursor.execute(
                """
                INSERT INTO canonical_building (
                    workspace_name, building_key, street_number, street_name, 
                    city, province, postal_code, country_code, latitude, longitude,
                    source_attribution
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) AS new_row
                ON DUPLICATE KEY UPDATE 
                    street_number = CASE
                        WHEN %s = 1 OR canonical_building.street_number IS NULL OR canonical_building.street_number = ''
                        THEN new_row.street_number ELSE canonical_building.street_number END,
                    street_name = CASE
                        WHEN %s = 1 OR canonical_building.street_name IS NULL OR canonical_building.street_name = ''
                        THEN new_row.street_name ELSE canonical_building.street_name END,
                    city = CASE
                        WHEN %s = 1 OR canonical_building.city IS NULL OR canonical_building.city = ''
                        THEN new_row.city ELSE canonical_building.city END,
                    province = CASE
                        WHEN %s = 1 OR canonical_building.province IS NULL OR canonical_building.province = ''
                        THEN new_row.province ELSE canonical_building.province END,
                    postal_code = CASE
                        WHEN %s = 1 OR canonical_building.postal_code IS NULL OR canonical_building.postal_code = ''
                        THEN new_row.postal_code ELSE canonical_building.postal_code END,
                    country_code = CASE
                        WHEN %s = 1 OR canonical_building.country_code IS NULL OR canonical_building.country_code = ''
                        THEN new_row.country_code ELSE canonical_building.country_code END,
                    latitude = COALESCE(new_row.latitude, canonical_building.latitude),
                    longitude = COALESCE(new_row.longitude, canonical_building.longitude),
                    updated_at = NOW(),
                    source_attribution = JSON_ARRAY_APPEND(COALESCE(canonical_building.source_attribution, '[]'), '$', %s)
                """,
                (
                    workspace_name, building_key, building_payload["street_number"], building_payload["street_name"],
                    building_payload["city"], building_payload["province"], building_payload["postal_code"], building_payload["country_code"],
                    building_payload["latitude"], building_payload["longitude"],
                    str(row["raw_id"]),
                    1 if row.get("reference_backed") else 0,
                    1 if row.get("reference_backed") else 0,
                    1 if row.get("reference_backed") else 0,
                    1 if row.get("reference_backed") else 0,
                    1 if row.get("reference_backed") else 0,
                    1 if row.get("reference_backed") else 0,
                    str(row["raw_id"])
                )
            )
            if cursor.rowcount == 1:
                buildings_added += 1

            # 3. Upsert Unit tied to the building key
            # 3. 更新/插入绑定至建筑键的单元
            u_num = _normalize_canonical_unit_value(row.get("suggested_unit_number"))
            if u_num:
                rows_with_units_processed += 1
                unit_key = hashlib.sha256(f"{building_key}|{u_num}".encode("utf-8")).hexdigest()
                unique_unit_keys_processed.add(unit_key)
                cursor.execute(
                    """
                    INSERT INTO canonical_unit (
                        workspace_name, unit_key, building_key, unit_number, source_attribution
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                        updated_at = NOW(),
                        source_attribution = JSON_ARRAY_APPEND(COALESCE(source_attribution, '[]'), '$', %s)
                    """,
                    (workspace_name, unit_key, building_key, u_num, str(row["raw_id"]), str(row["raw_id"]))
                )
                _consolidate_canonical_unit_variants(cursor, workspace_name, building_key, u_num, unit_key)
                if cursor.rowcount == 1:
                    units_added += 1
        
        conn.commit()

    logger.info("Asset consolidation complete. New B: %d, New U: %d", buildings_added, units_added)
    
    return {
        "status": "success",
        "new_buildings": buildings_added,
        "new_units": units_added,
        "promoted_buildings": buildings_added,
        "promoted_units": units_added,
        "total_processed": len(results),
        "reference_backed_rows_processed": reference_backed_rows_processed,
        "non_reference_rows_processed": non_reference_rows_processed,
        "rows_with_units_processed": rows_with_units_processed,
        "unique_building_keys_processed": len(unique_building_keys_processed),
        "unique_unit_keys_processed": len(unique_unit_keys_processed),
    }

def get_asset_stats(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME) -> dict[str, Any]:
    """
    Retrieves statistics from the canonical tables.
    从标准资产表中检索统计数据。
    """
    b_count = fetch_all("SELECT COUNT(*) as cnt FROM canonical_building WHERE workspace_name = %s", (workspace_name,))
    u_count = fetch_all("SELECT COUNT(*) as cnt FROM canonical_unit WHERE workspace_name = %s", (workspace_name,))
    
    return {
        "total_buildings": b_count[0]["cnt"] if b_count else 0,
        "total_units": u_count[0]["cnt"] if u_count else 0,
        "workspace": workspace_name
    }
