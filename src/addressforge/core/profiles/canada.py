from __future__ import annotations
import re
from typing import Any, List, Tuple, Pattern
from .base import BaseCountryProfile

class CanadaProfile(BaseCountryProfile):
    """
    Canada-specific implementation for North American address governance.
    加拿大特定的北美地址治理实现。
    """

    @property
    def country_code(self) -> str:
        return "CA"

    @property
    def default_city(self) -> str:
        return "Halifax"

    @property
    def default_province(self) -> str:
        return "NS"

    @property
    def province_tokens(self) -> set[str]:
        return {"NS", "NB", "PE", "NL", "QC", "ON", "MB", "SK", "AB", "BC", "YT", "NT", "NU"}

    @property
    def postal_code_pattern(self) -> str:
        return r"^[A-Z]\d[A-Z]\s*\d[A-Z]\d$"

    @property
    def gps_bounds(self) -> dict[str, float]:
        return {
            "lat_min": 43.5, "lat_max": 47.0,
            "lon_min": -66.0, "lon_max": -60.0,
        }

    @property
    def parsing_patterns(self) -> List[Tuple[Pattern, str, float, float]]:
        # Encapsulated patterns previously in common.py
        # 封装之前位于 common.py 中的模式
        unit_kw = r"(?:UNIT|APT|SUITE|STE|RM|ROOM|BSMT|BASEMENT|PH|PENTHOUSE|FL|FLOOR)"
        
        return [
            (re.compile(rf"^\s*(BSMT|BASEMENT|SUITE|STE|UNIT|APT)\s*([A-Za-z0-9-]+)\s+(\d+[A-Za-z]?)\s+([^,]+)", re.IGNORECASE), "comm_prefix_label", 0.90, 0.95),
            (re.compile(rf"^\s*([A-Za-z0-9-]+)\s*-\s*(\d+[A-Za-z]?)\s+([^,]+)", re.IGNORECASE), "leading_hyphen", 0.95, 0.98),
            (re.compile(rf"^\s*#\s*([A-Za-z0-9-]+)\s+(\d+[A-Za-z]?)\s+([^,]+)", re.IGNORECASE), "hash_prefix", 0.92, 0.95),
            (re.compile(rf"^\s*(LEVEL|FLOOR|FL)\s*(\d+)\s+(\d+[A-Za-z]?)\s+([^,]+)", re.IGNORECASE), "level_prefix", 0.95, 0.98),
            (re.compile(rf"^\s*(?:{unit_kw}\s*[\w-]+\s+)?(\d+[A-Za-z]?)\s+([^,]+)", re.IGNORECASE), "street_standard", 0.85, 0.80)
        ]

    def normalize_province(self, value: str | None) -> str | None:
        if not value: return None
        v = value.strip().upper().replace(".", "")
        mapping = {
            "NOVA SCOTIA": "NS", "NEW BRUNSWICK": "NB", "ONTARIO": "ON", "QUEBEC": "QC"
        }
        return mapping.get(v, v) if v in self.province_tokens or v in mapping else None

    def canonical_postal_code(self, value: str | None) -> str | None:
        if not value: return None
        m = re.search(r"([A-Z]\d[A-Z])\s*(\d[A-Z]\d)", value.upper())
        return f"{m.group(1)} {m.group(2)}" if m else None
