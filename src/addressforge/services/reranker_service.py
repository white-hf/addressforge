import os
import json
import re
from pathlib import Path
from typing import Any, Dict, List
from catboost import CatBoostClassifier
from addressforge.core.features import get_feature_engine
from addressforge.core.utils import logger

def _is_same_base_address(cand: dict, anchor: dict) -> bool:
    cand_base = str(cand.get("base_address_key") or "").strip()
    anchor_base = str(anchor.get("base_address_key") or "").strip()
    if cand_base and anchor_base and cand_base == anchor_base:
        return True
        
    # Structural fallback
    c_num = str(cand.get("street_number") or "").strip().upper()
    a_num = str(anchor.get("street_number") or "").strip().upper()
    if not c_num or c_num != a_num:
        return False
        
    c_prov = str(cand.get("province") or "").strip().upper()
    a_prov = str(anchor.get("province") or "").strip().upper()
    if not c_prov or c_prov != a_prov:
        return False
        
    c_city = str(cand.get("city") or "").strip().upper()
    a_cities = [str(anchor.get(k) or "").strip().upper() for k in ["city", "municipality", "community"] if anchor.get(k)]
    if not c_city or not any(c_city == ac or ac in c_city or c_city in ac for ac in a_cities):
        return False
        
    c_street = str(cand.get("street_name") or "").strip().upper()
    a_street = str(anchor.get("street_name") or "").strip().upper()
    if not c_street or not a_street:
        return False
        
    if c_street == a_street:
        return True
        
    suffix_map = {
        "ROAD": "RD", "RD": "RD",
        "STREET": "ST", "ST": "ST",
        "AVENUE": "AVE", "AVE": "AVE",
        "BOULEVARD": "BLVD", "BLVD": "BLVD",
        "LANE": "LN", "LN": "LN",
        "DRIVE": "DR", "DR": "DR",
        "COURT": "CRT", "CRT": "CRT",
        "CIRCLE": "CIR", "CIR": "CIR",
        "HIGHWAY": "HWY", "HWY": "HWY",
        "TRAIL": "TRL", "TRL": "TRL",
        "PLACE": "PL", "PL": "PL",
        "TERRACE": "TER", "TER": "TER",
    }
    
    def normalize_name(s: str) -> set[str]:
        return {suffix_map.get(t, t) for t in s.split() if t}
        
    return normalize_name(c_street) == normalize_name(a_street)


class RerankerService:
    def __init__(self, manifest: Dict[str, Any] | None = None):
        # Removed Singleton guard for Phase 16 version alignment
        # 移除单例守卫以实现第 16 阶段的版本对齐
        self._artifact_source = "fallback"
        if manifest and manifest.get("reranker_model_artifact"):
            rma = manifest["reranker_model_artifact"]
            self.model_path = Path(rma.get("model_path") or "runtime/models/reranker_catboost_v1.cbm")
            self._artifact_source = "manifest"
        else:
            self.model_path = Path("runtime/models/reranker_catboost_v1.cbm")
            if self.model_path.exists():
                self._artifact_source = "legacy_path"

        self.model = None
        self.feature_extractor = get_feature_engine()
        self._load_model()

    def _load_model(self):
        if self.model_path.exists():
            try:
                self.model = CatBoostClassifier()
                self.model.load_model(str(self.model_path))
                logger.info("Reranker model loaded from %s", self.model_path)
            except Exception as e:
                logger.error("Failed to load reranker model: %s", e)
        else:
            logger.warning("Reranker model not found at %s. Using heuristic fallback.", self.model_path)

    def reload_models(self, manifest: Dict[str, Any] | None = None) -> None:
        """
        Hot-reloads the ML models from disk.
        从磁盘热重载 ML 模型。
        """
        logger.info("Hot-reloading Reranker model...")
        if manifest and manifest.get("reranker_model_artifact"):
            rma = manifest["reranker_model_artifact"]
            self.model_path = Path(rma.get("model_path") or "runtime/models/reranker_catboost_v1.cbm")
            
        self._load_model()

    def describe_runtime(self) -> dict[str, Any]:
        """
        Returns the runtime identity of the reranker model.
        返回重排模型的运行时标识。
        """
        return {
            "model_path": str(self.model_path),
            "model_type": "catboost",
            "artifact_source": self._artifact_source,
            "feature_schema_version": "28d_ufm",
        }

    def rerank_candidates(
        self, 
        raw_text: str, 
        candidates: List[Dict[str, Any]],
        semantic_anchors: List[Dict[str, Any]] | None = None
    ) -> List[Dict[str, Any]]:
        """
        Reranks a list of parser candidates using the ML model.
        使用 ML 模型对解析候选列表进行重排。
        """
        if not self.model or not candidates:
            return sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)
        
        try:
            # First pass: find the top heuristic score
            best_h_score = max([float(c.get("score") or 0.5) for c in candidates]) if candidates else 0.5
            
            scored_candidates = []
            for cand in candidates:
                parsed = cand.get("parsed", {})
                parser_name = cand.get("parser_name", "unknown")
                
                # Phase 13: Calculate semantic alignment score if anchors available
                # 第 13 阶段：如果锚点可用，计算语义对齐分
                semantic_alignment = 0.0
                if semantic_anchors:
                    # Compare cand base key/structure with top anchor keys/structures
                    for anchor in semantic_anchors:
                        if _is_same_base_address(parsed, anchor):
                            if not anchor.get("gps_conflict", False):
                                semantic_alignment = max(semantic_alignment, anchor.get("vector_score", 0.9))
                
                # Extract features for this candidate
                features = self.feature_extractor.extract_features(
                    raw_text, 
                    parsed, 
                    parser_name,
                    best_candidate_score=best_h_score
                )
                
                # New Phase 13 Feature: Semantic Alignment
                # 新增第 13 阶段特征：语义对齐度
                features["semantic_alignment"] = float(semantic_alignment)
                
                vector = self.feature_extractor.vectorize(features)
                
                # Predict probability of being the correct one
                # target=1 is 'correct'
                prob = float(self.model.predict_proba([vector])[0][1])
                
                # Add rerank_score to the candidate
                cand_copy = dict(cand)
                cand_copy["rerank_score"] = round(prob, 4)
                cand_copy["semantic_alignment"] = round(semantic_alignment, 4)
                
                # Weighted blend: Original + ML + Semantic
                # 加权融合：原始分 + ML 分 + 语义分
                cand_copy["final_score"] = round(0.2 * cand.get("score", 0.5) + 0.5 * prob + 0.3 * semantic_alignment, 4)
                scored_candidates.append(cand_copy)
            
            # Sort by final score
            return sorted(scored_candidates, key=lambda x: x.get("final_score", 0), reverse=True)
            
        except Exception as e:
            logger.error("Reranking error: %s", e)
            return sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)

def get_reranker_service(manifest: Dict[str, Any] | None = None) -> RerankerService:
    """
    Returns a new instance of RerankerService.
    返回 RerankerService 的新实例。
    """
    return RerankerService(manifest=manifest)


def build_reranker_service_from_manifest(manifest: Dict[str, Any] | None) -> RerankerService:
    """
    Builds a RerankerService instance from a versioned manifest.
    根据版本化的清单构建 RerankerService 实例。
    """
    return RerankerService(manifest=manifest)
