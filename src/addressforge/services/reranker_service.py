import os
import json
from pathlib import Path
from typing import Any, Dict, List
from catboost import CatBoostClassifier
from addressforge.core.features import get_feature_engine
from addressforge.core.utils import logger

class RerankerService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RerankerService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self.model_path = Path("runtime/models/reranker_catboost_v1.cbm")
        self.model = None
        self.feature_extractor = get_feature_engine()
        self._load_model()
        self._initialized = True

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

    def rerank_candidates(self, raw_text: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
                
                # Extract features for this candidate
                features = self.feature_extractor.extract_features(
                    raw_text, 
                    parsed, 
                    parser_name,
                    best_candidate_score=best_h_score
                )
                vector = self.feature_extractor.vectorize(features)
                
                # Predict probability of being the correct one
                # target=1 is 'correct'
                prob = float(self.model.predict_proba([vector])[0][1])
                
                # Add rerank_score to the candidate
                cand_copy = dict(cand)
                cand_copy["rerank_score"] = round(prob, 4)
                # Weighted blend of original score and reranker score (for stability)
                cand_copy["final_score"] = round(0.3 * cand.get("score", 0.5) + 0.7 * prob, 4)
                scored_candidates.append(cand_copy)
            
            # Sort by final score
            return sorted(scored_candidates, key=lambda x: x.get("final_score", 0), reverse=True)
            
        except Exception as e:
            logger.error("Reranking error: %s", e)
            return sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)

_reranker_service = None

def get_reranker_service() -> RerankerService:
    global _reranker_service
    if _reranker_service is None:
        _reranker_service = RerankerService()
    return _reranker_service
