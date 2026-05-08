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
        # Encapsulated patterns for Canada
        # 封装加拿大的模式
        unit_kw = r"(?:UNIT|APT|SUITE|STE|RM|ROOM|BSMT|BASEMENT|PH|PENTHOUSE|FL|FLOOR)"
        
        return [
            # 1. Glued keyword and number (e.g. APT308 123 MAIN ST)
            # 1. 紧凑的关键字和数字 (例如 APT308 123 MAIN ST)
            (re.compile(rf"^\s*(BSMT|BASEMENT|SUITE|STE|UNIT|APT|RM|ROOM)([A-Za-z0-9/-]+)\s+(\d+[A-Za-z]?)\s+([^,]+)", re.IGNORECASE), "glued_comm_prefix", 0.91, 0.96),
            
            # 2. Standard commercial/unit prefix with space (e.g. UNIT 1302 123 MAIN ST) or sub-units (A/B, A-5)
            # 2. 带有空格的标准商业/单元前缀或子单元
            (re.compile(rf"^\s*(BSMT|BASEMENT|SUITE|STE|UNIT|APT|RM|ROOM)\s*([A-Za-z0-9/-]+)\s+(\d+[A-Za-z]?)\s+([^,]+)", re.IGNORECASE), "comm_prefix_label", 0.90, 0.95),
            
            # 3. Leading hyphen (e.g. 101-123 MAIN ST)
            # 3. 前导连字符 (例如 101-123 MAIN ST)
            (re.compile(rf"^\s*([A-Za-z0-9/-]+)\s*-\s*(\d+[A-Za-z]?)\s+([^,]+)", re.IGNORECASE), "leading_hyphen", 0.95, 0.98),
            
            # 4. Hash prefix (e.g. #203B 123 MAIN ST)
            # 4. 井号前缀 (例如 #203B 123 MAIN ST)
            (re.compile(rf"^\s*#\s*([A-Za-z0-9/-]+)\s+(\d+[A-Za-z]?)\s+([^,]+)", re.IGNORECASE), "hash_prefix", 0.92, 0.95),
            
            # 5. Level prefix (e.g. LEVEL 2 123 MAIN ST)
            # 5. 楼层前缀
            (re.compile(rf"^\s*(LEVEL|FLOOR|FL)\s*([A-Za-z0-9/-]+)\s+(\d+[A-Za-z]?)\s+([^,]+)", re.IGNORECASE), "level_prefix", 0.95, 0.98),
            
            # 6. Trailing explicit unit after street (e.g. 123 MAIN ST UNIT 128)
            # 6. 街道后的显式 unit 关键字，不再接受无关键字裸数字
            (re.compile(rf"^\s*(\d+[A-Za-z]?)\s+(.+?)\s+(?:{unit_kw}\s+([A-Za-z0-9/-]+))$", re.IGNORECASE), "trailing_unit", 0.88, 0.85),

            # 7. Street standard with optional prefix
            # 7. 带有可选前缀的街道标准格式
            (re.compile(rf"^\s*(?:{unit_kw}\s*[\w/-]+\s+)?(\d+[A-Za-z]?)\s+([^,]+)", re.IGNORECASE), "street_standard", 0.85, 0.80)
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
