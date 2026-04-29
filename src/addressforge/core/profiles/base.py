from __future__ import annotations
import re
from abc import ABC, abstractmethod
from typing import Any, List, Tuple, Pattern

class BaseCountryProfile(ABC):
    """
    Abstract base class for country-specific address logic and regional data.
    国家特定地址逻辑与区域数据的抽象基类。
    """

    @property
    @abstractmethod
    def country_code(self) -> str:
        """Returns the ISO 3166-1 alpha-2 country code."""
        pass

    @property
    @abstractmethod
    def default_city(self) -> str:
        """Default city for the target region (e.g., 'Halifax')."""
        pass

    @property
    @abstractmethod
    def default_province(self) -> str:
        """Default province/state abbreviation (e.g., 'NS')."""
        pass

    @property
    @abstractmethod
    def province_tokens(self) -> set[str]:
        """Returns the set of valid province/state abbreviations."""
        pass

    @property
    @abstractmethod
    def postal_code_pattern(self) -> str:
        """Regex pattern for valid postal codes."""
        pass

    @property
    @abstractmethod
    def gps_bounds(self) -> dict[str, float]:
        """Bounding box (lat/lon) for the country/region."""
        pass

    @property
    @abstractmethod
    def parsing_patterns(self) -> List[Tuple[Pattern, str, float, float]]:
        """
        List of (Regex, source_name, parse_confidence, unit_confidence) tuples.
        (正则表达式, 源名称, 解析置信度, 单元置信度) 元组列表。
        """
        pass

    @abstractmethod
    def normalize_province(self, value: str | None) -> str | None:
        """Normalizes a province/state into a standard abbreviation."""
        pass

    @abstractmethod
    def canonical_postal_code(self, value: str | None) -> str | None:
        """Standardizes the postal code format."""
        pass
