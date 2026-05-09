import os
from pathlib import Path
import json
from typing import Any, Dict, List
from catboost import CatBoostClassifier
from addressforge.core.features import get_feature_engine, AddressFeatureExtractor
from addressforge.core.utils import logger

# Proxy imports for legacy service functions
from addressforge.models.registry import (
    register_model_version as register_model,
    promote_model as promote,
    deprecate_model as deprecate,
    list_models as fetch_models
)

class ModelService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self.model_path = Path("runtime/models/decision_catboost_v1.cbm")
        self.model = None
        self.feature_extractor = get_feature_engine()
        self._load_model()
        self._initialized = True

    def _load_model(self):
        if self.model_path.exists():
            try:
                self.model = CatBoostClassifier()
                self.model.load_model(str(self.model_path))
                logger.info("Decision model loaded from %s", self.model_path)
            except Exception as e:
                logger.error("Failed to load decision model: %s", e)
        else:
            logger.warning("Decision model not found at %s. Serving in heuristic-only mode.", self.model_path)

    def predict_decision(
        self, 
        raw_text: str, 
        parsed: Dict[str, Any], 
        parser_name: str = "hybrid",
        validation_context: Dict[str, Any] | None = None,
        reference_context: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """
        Runs ML inference to predict P(accept).
        执行 ML 推断以预测 P(accept)。
        """
        if not self.model:
            return {"ml_score": 0.0, "status": "no_model"}
        
        try:
            features = self.feature_extractor.extract_features(
                raw_text, 
                parsed, 
                parser_name,
                validation_context=validation_context,
                reference_context=reference_context
            )
            vector = self.feature_extractor.vectorize(features)
            
            # CatBoost predict_proba returns [P(0), P(1), P(2)]
            # 0=reject, 1=accept, 2=review
            probs = self.model.predict_proba([vector])[0]
            
            # Map probabilities to class names
            # 将概率映射到类别名称
            class_map = {0: "reject", 1: "accept", 2: "review"}
            ml_decision_idx = int(self.model.predict([vector])[0][0])
            ml_decision = class_map.get(ml_decision_idx, "review")
            
            return {
                "ml_score": round(float(probs[ml_decision_idx]), 4),
                "probabilities": {class_map[i]: round(float(probs[i]), 4) for i in range(len(probs))},
                "status": "success",
                "ml_decision": ml_decision
            }
        except Exception as e:
            logger.error("ML Inference error: %s", e)
            return {"ml_score": 0.0, "status": "error", "error": str(e)}

_model_service = None

def get_model_service() -> ModelService:
    global _model_service
    if _model_service is None:
        _model_service = ModelService()
    return _model_service
