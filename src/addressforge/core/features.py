"""
AddressForge Universal Feature Matrix (UFM)
==========================================
Centralized engine for address feature extraction. 
Unifies features from supervised_baseline.py and heuristic signals.

地址治理通用特征矩阵 (UFM)
========================
集中式地址特征提取引擎。
统一了来自 supervised_baseline.py 的特征及启发式信号。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

# --- Constants & Knowledge Base ---

_PROVINCES = {"NS", "ON", "BC", "AB", "QC", "MB", "SK", "NB", "PE", "NL", "YT", "NT", "NU"}

# Regex for common Canadian address patterns
_UNIT_HINT_RE = re.compile(r"\b(APT|UNIT|SUITE|STE|RM|ROOM|BSMT|BASEMENT|PH|LOBBY|FL|FLOOR)\b", re.I)
_NUMBERED_ROAD_RE = re.compile(r"\b(HWY|HIGHWAY|ROUTE|RTE|TRUNK|NS|CANADA)\s+\d+\b", re.I)
_DIRECTIONAL_RE = re.compile(r"\b(N|S|E|W|NORTH|SOUTH|EAST|WEST|NW|NE|SW|SE)\b", re.I)
_DIGIT_BLOCK_RE = re.compile(r"\b\d+\b")

class AddressFeatureExtractor:
    """
    Extracts a high-dimensional feature vector from an address parsing attempt.
    从地址解析尝试中提取高维特征向量。
    """

    def __init__(self, valid_cities: set[str] | None = None):
        self.valid_cities = valid_cities or set()

    def extract_features(
        self, 
        raw_text: str, 
        parsed: Dict[str, Any], 
        parser_name: str = "unknown",
        validation_context: Dict[str, Any] | None = None,
        reference_context: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """
        Main entry point for feature extraction.
        特征提取的主入口。
        """
        features = {}
        val_ctx = validation_context or {}
        ref_ctx = reference_context or {}
        hints = val_ctx.get("hints", {})
        
        # 1. Lexical Signals (词法信号)
        raw_text = str(raw_text or "")
        features["text_len"] = len(raw_text)
        features["token_count"] = len(raw_text.split())
        features["digit_block_count"] = len(_DIGIT_BLOCK_RE.findall(raw_text))
        features["has_comma"] = 1 if "," in raw_text else 0
        features["has_hyphen"] = 1 if "-" in raw_text else 0
        features["has_directional"] = 1 if _DIRECTIONAL_RE.search(raw_text) else 0

        # 2. Structural Integrity (结构完整性)
        features["has_street_number"] = 1 if parsed.get("street_number") else 0
        features["has_street_name"] = 1 if parsed.get("street_name") else 0
        features["has_unit"] = 1 if parsed.get("unit_number") else 0
        features["has_city"] = 1 if parsed.get("city") else 0
        features["has_postal"] = 1 if parsed.get("postal_code") else 0

        # 3. Domain Constraint Alignment (值域约束对齐)
        city = (parsed.get("city") or "").upper().strip()
        province = (parsed.get("province") or "").upper().strip()
        
        features["is_province_valid"] = 1 if province in _PROVINCES else 0
        features["is_city_valid"] = 1 if city in self.valid_cities else 0
        
        # 4. Disambiguation & Suspicion (歧义与可疑检测)
        sn = parsed.get("street_number")
        un = parsed.get("unit_number")
        
        # Suspicion: Unit is identical to Street Number (e.g., "307 - 307")
        features["is_unit_redundant"] = 1 if sn and un and str(sn) == str(un) else 0
        
        # Suspicion: Double Number pattern detected
        features["has_double_number"] = 1 if features["digit_block_count"] >= 2 else 0
        
        # Suspicion: Numbered Road vs Unit Number
        features["is_numbered_road"] = 1 if _NUMBERED_ROAD_RE.search(raw_text) else 0
        features["has_hwy_keyword"] = 1 if re.search(r"\b(HWY|HIGHWAY)\b", raw_text, re.I) else 0
        
        # 5. Validation & Reference Signals (验证与参考信号)
        features["confidence"] = float(val_ctx.get("confidence", 0.5))
        features["reference_score"] = float(hints.get("reference_score", 0.0))
        features["gps_conflict"] = 1 if hints.get("gps_conflict") else 0
        features["parser_disagreement"] = 1 if hints.get("parser_disagreement") else 0
        
        # 6. Semantic Hints (语义暗示)
        features["has_explicit_unit_hint"] = 1 if _UNIT_HINT_RE.search(raw_text) else 0
        
        # 7. Parser Provenance (解释器来源)
        features["parser_source"] = parser_name
        features["parse_confidence"] = float(parsed.get("parse_confidence", 0.5))

        return features

    def vectorize(self, feature_dict: Dict[str, Any]) -> List[float]:
        """
        Converts feature dict to a strictly numerical list for ML consumption.
        将特征字典转换为供 ML 使用的纯数值列表。
        """
        ordered_keys = [
            "text_len", "token_count", "digit_block_count", 
            "has_comma", "has_hyphen", "has_directional",
            "has_street_number", "has_street_name", "has_unit", 
            "has_city", "has_postal", "is_province_valid", 
            "is_city_valid", "is_unit_redundant", "has_double_number", 
            "is_numbered_road", "has_hwy_keyword", "has_explicit_unit_hint",
            "confidence", "reference_score", "gps_conflict", "parser_disagreement",
            "parse_confidence"
        ]
        return [float(feature_dict.get(k, 0)) for k in ordered_keys]

def get_feature_engine(workspace_name: str = "default") -> AddressFeatureExtractor:
    """
    Factory to create an engine with initialized knowledge bases.
    """
    return AddressFeatureExtractor()
