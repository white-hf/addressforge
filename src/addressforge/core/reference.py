from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .utils import logger
from .common import (
    create_run,
    db_cursor,
    dumps_payload,
    executemany_chunked,
    finish_run,
    fetch_all,
    haversine_meters,
    log_run_exception,
    normalize_city,
    normalize_space,
    normalize_street_name,
)


REFERENCE_FILE_ENV = "ADDRESSFORGE_REFERENCE_FILE"


@dataclass(frozen=True)
class ExternalBuildingReferenceRow:
    source_name: str
    external_id: str
    segment_id: str | None
    street_number: str
    street_name: str
    unit_number: str | None
    city: str
    municipality: str | None
    county: str | None
    province: str
    postal_code: str | None
    reference_lat: float | None
    reference_lon: float | None
    reference_tier: str
    quality_score: float
    raw_payload: dict


@dataclass(frozen=True)
class ReferenceMatchResult:
    reference: dict[str, object]
    score: float
    candidate_count: int
    unit_count_hint: int
    unit_numbers: tuple[str, ...]


def _normalize_unit(value: str | None) -> str | None:
    text = normalize_space(value).upper().lstrip("#")
    return text or None


def _is_valid_ns_coordinate(lat: str | float | None, lon: str | float | None) -> bool:
    try:
        lat_value = float(lat)
        lon_value = float(lon)
    except (TypeError, ValueError):
        return False
    return 43.0 <= lat_value <= 47.5 and -67.5 <= lon_value <= -58.0


def _resolve_geonova_source(csv_path: str | None = None) -> tuple[Iterable[dict[str, str]], str]:
    source_path = csv_path or os.getenv(REFERENCE_FILE_ENV)
    if not source_path:
        raise FileNotFoundError(
            "No reference source configured. Set ADDRESSFORGE_REFERENCE_FILE or pass csv_path."
        )
    path = Path(source_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Reference source file not found: {path}")
    handle = path.open("r", encoding="utf-8-sig", newline="")
    return csv.DictReader(handle), str(path)


class GeoNovaReferenceMatcher:
    def __init__(self) -> None:
        self._reference_map: dict[str, list[dict[str, object]]] | None = None

    def _coarse_reference_key(self, row: dict[str, object]) -> str:
        return "|".join(
            [
                str(row.get("street_number") or "").upper(),
                str(row.get("street_name") or "").upper(),
                str(row.get("province") or "").upper(),
            ]
        )

    def _load_reference_map(self) -> dict[str, list[dict[str, object]]]:
        if self._reference_map is not None:
            return self._reference_map
        rows = fetch_all(
            """
            SELECT
                reference_id,
                source_name,
                external_id,
                street_number,
                street_name,
                unit_number,
                city,
                municipality,
                county,
                province,
                postal_code,
                reference_lat,
                reference_lon,
                reference_tier,
                quality_score,
                is_active
            FROM external_building_reference
            WHERE is_active = 1
            """
        )
        reference_map: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            key = self._coarse_reference_key(row)
            reference_map.setdefault(key, []).append(row)
        self._reference_map = reference_map
        return reference_map

    def _city_compatible(self, left: str | None, right: str | None) -> bool:
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

    def _gps_score(self, lat: float | None, lon: float | None, reference_lat: float | None, reference_lon: float | None) -> float:
        if lat is None or lon is None or reference_lat is None or reference_lon is None:
            return 0.55 if reference_lat is not None and reference_lon is not None else 0.25
        distance = haversine_meters(lat, lon, reference_lat, reference_lon)
        if distance <= 20:
            return 1.0
        if distance <= 60:
            return 0.9
        if distance <= 120:
            return 0.78
        if distance <= 250:
            return 0.62
        return 0.25

    def match(
        self,
        street_number: str | None,
        street_name: str | None,
        province: str | None,
        city: str | None = None,
        municipality: str | None = None,
        county: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
    ) -> ReferenceMatchResult | None:
        if not street_number or not street_name or not province:
            return None
        key = "|".join([street_number.upper(), street_name.upper(), province.upper()])
        candidates = self._load_reference_map().get(key, [])
        if not candidates:
            return None

        observed_localities = tuple(value for value in {normalize_city(city), normalize_city(municipality), normalize_city(county)} if value)
        best_reference: dict[str, object] | None = None
        best_score = 0.0
        unit_numbers: set[str] = set()
        for reference in candidates:
            unit_value = str(reference.get("unit_number") or "").strip().upper()
            if unit_value:
                unit_numbers.add(unit_value)
            locality_match = 1.0 if any(self._city_compatible(locality, reference.get("city") or reference.get("municipality") or reference.get("county")) for locality in observed_localities or (normalize_city(city),)) else 0.0
            gps_score = self._gps_score(
                lat,
                lon,
                float(reference["reference_lat"]) if reference.get("reference_lat") is not None else None,
                float(reference["reference_lon"]) if reference.get("reference_lon") is not None else None,
            )
            score = round(
                0.45 * locality_match
                + 0.30 * gps_score
                + 0.25 * float(reference.get("quality_score") or 0.0),
                4,
            )
            if score > best_score:
                best_score = score
                best_reference = dict(reference)
        if best_reference is None:
            return None
        if len(candidates) == 1 and best_score < 0.70:
            return None
        if len(candidates) > 1 and best_score < 0.78:
            return None
        return ReferenceMatchResult(
            reference=best_reference,
            score=best_score,
            candidate_count=len(candidates),
            unit_count_hint=len(unit_numbers),
            unit_numbers=tuple(sorted(unit_numbers)),
        )


def _to_reference_row(row: dict[str, str]) -> ExternalBuildingReferenceRow | None:
    street_number = normalize_space(row.get("CIVICNUM")).upper()
    street_name = normalize_street_name(
        " ".join(
            token
            for token in [
                row.get("STRPREFIX"),
                row.get("STRNAME"),
                row.get("STRSUFFIX"),
                row.get("STRDIR"),
            ]
            if normalize_space(token)
        )
    )
    if not street_number or not street_name:
        return None
    city = normalize_city(row.get("COMM")) or normalize_city(row.get("MUN")) or "Halifax"
    municipality = normalize_city(row.get("MUN"))
    county = normalize_space(row.get("COUNTY")) or None
    lat = float(row["LAT"]) if _is_valid_ns_coordinate(row.get("LAT"), row.get("LONG")) else None
    lon = float(row["LONG"]) if _is_valid_ns_coordinate(row.get("LAT"), row.get("LONG")) else None
    return ExternalBuildingReferenceRow(
        source_name="geonova",
        external_id=str(row.get("PNTID") or ""),
        segment_id=normalize_space(row.get("SEGID")) or None,
        street_number=street_number,
        street_name=street_name,
        unit_number=_normalize_unit(row.get("UNIT_NUM")),
        city=city,
        municipality=municipality,
        county=county,
        province="NS",
        postal_code=None,
        reference_lat=lat,
        reference_lon=lon,
        reference_tier="authoritative",
        quality_score=0.95 if lat is not None and lon is not None else 0.82,
        raw_payload={
            "comm_id": normalize_space(row.get("COMM_ID")) or None,
            "community": city,
            "municipality": municipality,
            "county": county,
            "the_geom": normalize_space(row.get("the_geom")) or None,
            "add_loc": normalize_space(row.get("ADD_LOC")) or None,
            "civic_suffix": normalize_space(row.get("CIVSUFFIX")) or None,
        },
    )


class ExternalReferenceImportService:
    def _upsert_rows(self, rows: list[ExternalBuildingReferenceRow], run_id: int) -> int:
        if not rows:
            return 0
        query = """
            INSERT INTO external_building_reference (
                source_name, external_id, segment_id, street_number, street_name, unit_number,
                city, municipality, county, province, postal_code, reference_lat, reference_lon,
                reference_tier, quality_score, raw_payload, is_active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE
                segment_id = VALUES(segment_id),
                street_number = VALUES(street_number),
                street_name = VALUES(street_name),
                unit_number = VALUES(unit_number),
                city = VALUES(city),
                municipality = VALUES(municipality),
                county = VALUES(county),
                province = VALUES(province),
                postal_code = VALUES(postal_code),
                reference_lat = VALUES(reference_lat),
                reference_lon = VALUES(reference_lon),
                reference_tier = VALUES(reference_tier),
                quality_score = VALUES(quality_score),
                raw_payload = VALUES(raw_payload),
                is_active = 1,
                updated_at = CURRENT_TIMESTAMP
        """
        payload = [
            (
                item.source_name,
                item.external_id,
                item.segment_id,
                item.street_number,
                item.street_name,
                item.unit_number,
                item.city,
                item.municipality,
                item.county,
                item.province,
                item.postal_code,
                item.reference_lat,
                item.reference_lon,
                item.reference_tier,
                item.quality_score,
                dumps_payload({**item.raw_payload, "import_run_id": run_id}),
            )
            for item in rows
            if item.external_id
        ]
        with db_cursor() as (conn, cursor):
            executemany_chunked(cursor, query, payload, chunk_size=500)
            conn.commit()
            return len(payload)

    def run(self, csv_path: str | None = None, batch_size: int = 5000) -> dict[str, int | str]:
        run_id = create_run("evidence_aggregate", notes=f"geonova_import batch_size={batch_size}")
        try:
            reader, source = _resolve_geonova_source(csv_path)
            total = 0
            upserted = 0
            invalid = 0
            batch: list[ExternalBuildingReferenceRow] = []
            for raw_row in reader:
                reference_row = _to_reference_row(raw_row)
                if reference_row is None:
                    invalid += 1
                    continue
                batch.append(reference_row)
                total += 1
                if len(batch) >= batch_size:
                    upserted += self._upsert_rows(batch, run_id)
                    batch.clear()
            if batch:
                upserted += self._upsert_rows(batch, run_id)
            finish_run(
                run_id,
                "completed",
                notes=dumps_payload(
                    {
                        "source": source,
                        "rows_seen": total + invalid,
                        "valid_rows": total,
                        "invalid_rows": invalid,
                        "upserted": upserted,
                    }
                ),
            )
            logger.info(
                "External reference import run %s completed: source=%s valid=%s invalid=%s upserted=%s",
                run_id,
                source,
                total,
                invalid,
                upserted,
            )
            return {
                "run_id": run_id,
                "source": source,
                "rows_seen": total + invalid,
                "valid_rows": total,
                "invalid_rows": invalid,
                "upserted": upserted,
            }
        except Exception as exc:
            log_run_exception(run_id, exc)
            raise


GeoNovaReferenceImportService = ExternalReferenceImportService
