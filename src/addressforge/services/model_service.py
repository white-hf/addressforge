import os
from pathlib import Path
import json
import pickle
from typing import Any, Dict, List
from catboost import CatBoostClassifier
from addressforge.core.decision_features import (
    DECISION_LABELS,
    build_decision_inference_feature_row,
    build_decision_inference_frame,
)
from addressforge.core.features import get_feature_engine
from addressforge.core.utils import logger

# Proxy imports for legacy service functions
from addressforge.models.registry import (
    register_model_version as register_model,
    promote_model as promote,
    deprecate_model as deprecate,
    list_models as fetch_models
)

def _path_or_none(value: Any) -> Path | None:
    if value in (None, ""):
        return None
    return Path(str(value))


class ModelService:
    def __init__(
        self,
        *,
        metadata_path: str | Path | None = None,
        model_path: str | Path | None = None,
        legacy_model_path: str | Path | None = None,
        manifest: Dict[str, Any] | None = None,
    ):
        # Removed Singleton guard for Phase 16/17 version alignment
        # 移除单例守卫以实现第 16/17 阶段的版本对齐
        self.model_path = _path_or_none(model_path) or Path(
            os.getenv("ADDRESSFORGE_DECISION_MODEL_PKL_PATH", "runtime/models/decision_catboost_v1.pkl")
        )
        self.metadata_path = _path_or_none(metadata_path) or Path(
            os.getenv("ADDRESSFORGE_DECISION_MODEL_METADATA_PATH", "runtime/models/decision_catboost_v1.json")
        )
        self.legacy_model_path = _path_or_none(legacy_model_path) or Path(
            os.getenv("ADDRESSFORGE_DECISION_MODEL_CBM_PATH", "runtime/models/decision_catboost_v1.cbm")
        )
        
        # Phase 17/18: Support version-aware BuildingType and Decision models
        # 第 17/18 阶段：支持识别版本的 BuildingType 和 Decision 模型
        if manifest:
            # Override paths from manifest if provided
            # 如果提供了清单，则覆盖路径
            if manifest.get("decision_model_artifact"):
                dma = manifest["decision_model_artifact"]
                if dma.get("metadata_path"): self.metadata_path = Path(dma["metadata_path"])
                if dma.get("model_path"): self.model_path = Path(dma["model_path"])
                if dma.get("legacy_model_path"): self.legacy_model_path = Path(dma["legacy_model_path"])
            
            if manifest.get("building_type_model_artifact"):
                btma = manifest["building_type_model_artifact"]
                self.bt_model_path = Path(btma.get("model_path") or "runtime/models/building_type_catboost_v1.cbm")
            else:
                self.bt_model_path = Path("runtime/models/building_type_catboost_v1.cbm")
        else:
            self.bt_model_path = Path("runtime/models/building_type_catboost_v1.cbm")

        self.model = None
        self.bt_model = None
        self.model_payload: Dict[str, Any] | None = None
        self.metadata: Dict[str, Any] = {}
        self.feature_names: List[str] = []
        self.present_labels: List[str] = list(DECISION_LABELS)
        self._legacy_mode = False
        self.feature_extractor = get_feature_engine()
        self._load_model()

    def _load_model(self):
        if self.metadata_path.exists() and self.model_path.exists():
            try:
                self.metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
                with self.model_path.open("rb") as fh:
                    self.model_payload = pickle.load(fh)
                self.model = self.model_payload.get("estimator")
                self.feature_names = list(
                    self.metadata.get("catboost_feature_names")
                    or self.model_payload.get("feature_names")
                    or []
                )
                self.present_labels = list(self.metadata.get("present_labels") or self.model_payload.get("present_labels") or list(DECISION_LABELS))
                self._legacy_mode = False
                logger.info(
                    "Decision model loaded from %s with metadata %s",
                    self.model_path,
                    self.metadata_path,
                )
            except Exception as e:
                logger.error("Failed to load decision model: %s", e)
                self.model = None
                self.model_payload = None
        elif self.legacy_model_path.exists():
            try:
                self.model = CatBoostClassifier()
                self.model.load_model(str(self.legacy_model_path))
                self._legacy_mode = True
                logger.warning(
                    "Decision model loaded from legacy CatBoost artifact %s without schema sidecar; serving in compatibility mode.",
                    self.legacy_model_path,
                )
            except Exception as e:
                logger.error("Failed to load legacy decision model: %s", e)
                self.model = None
        else:
            logger.warning(
                "Decision model not found at %s / %s. Serving in heuristic-only mode.",
                self.model_path,
                self.legacy_model_path,
            )

        # Load BuildingType model
        # 加载 BuildingType 模型
        if self.bt_model_path.exists():
            try:
                self.bt_model = CatBoostClassifier()
                self.bt_model.load_model(str(self.bt_model_path))
                logger.info("BuildingType model loaded from %s", self.bt_model_path)
            except Exception as e:
                logger.error("Failed to load building_type model: %s", e)
        else:
            logger.info("BuildingType model not found at %s.", self.bt_model_path)

    def reload_models(self, manifest: Dict[str, Any] | None = None) -> None:
        """
        Hot-reloads the ML models from disk.
        从磁盘热重载 ML 模型。
        """
        logger.info("Hot-reloading Decision and BuildingType models...")
        if manifest:
            # Phase 17/18: Support version-aware BuildingType and Decision models
            # 第 17/18 阶段：支持识别版本的 BuildingType 和 Decision 模型
            if manifest.get("decision_model_artifact"):
                dma = manifest["decision_model_artifact"]
                self.metadata_path = Path(dma.get("metadata_path") or self.metadata_path)
                self.model_path = Path(dma.get("model_path") or self.model_path)
                self.legacy_model_path = Path(dma.get("legacy_model_path") or self.legacy_model_path)
            
            if manifest.get("building_type_model_artifact"):
                btma = manifest["building_type_model_artifact"]
                self.bt_model_path = Path(btma.get("model_path") or "runtime/models/building_type_catboost_v1.cbm")
            else:
                self.bt_model_path = Path("runtime/models/building_type_catboost_v1.cbm")
        
        self._load_model()

    def describe_runtime(self) -> dict[str, Any]:
        return {
            "model_type": str(self.metadata.get("model_type") or self.model_payload.get("model_type") if self.model_payload else ""),
            "metadata_path": str(self.metadata_path),
            "model_path": str(self.model_path),
            "legacy_model_path": str(self.legacy_model_path),
            "legacy_mode": self._legacy_mode,
            "present_labels": list(self.present_labels),
            "feature_names": list(self.feature_names),
        }

    def predict_building_type(
        self, 
        raw_text: str, 
        parsed: Dict[str, Any], 
        parser_name: str = "hybrid", 
        validation_context: Dict[str, Any] | None = None, 
        reference_context: Dict[str, Any] | None = None, 
        semantic_alignment: float | None = None
    ) -> Dict[str, Any]:
        """
        Runs ML inference to predict building type.
        执行 ML 推断以预测建筑类型。
        """
        if not self.bt_model:
            return {"status": "no_model"}
            
        try:
            features = self.feature_extractor.extract_features(
                raw_text, 
                parsed, 
                parser_name,
                validation_context=validation_context,
                reference_context=reference_context,
                semantic_alignment=semantic_alignment
            )
            vector = self.feature_extractor.vectorize(features)
            
            probs = self.bt_model.predict_proba([vector])[0]
            
            # 0 = single_unit, 1 = multi_unit, 2 = commercial
            class_map = {0: "single_unit", 1: "multi_unit", 2: "commercial"}
            ml_bt_idx = int(self.bt_model.predict([vector])[0][0])
            ml_bt = class_map.get(ml_bt_idx, "single_unit")
            
            return {
                "status": "success",
                "ml_building_type": ml_bt,
                "probabilities": {class_map[i]: round(float(probs[i]), 4) for i in range(len(probs))}
            }
        except Exception as e:
            logger.error("ML BuildingType Inference error: %s", e)
            return {"status": "error", "error": str(e)}

    def predict_decision(
        self, 
        raw_text: str, 
        parsed: Dict[str, Any], 
        parser_name: str = "hybrid",
        validation_context: Dict[str, Any] | None = None,
        reference_context: Dict[str, Any] | None = None,
        *,
        building_type: str | None = None,
        current_decision: str | None = None,
    ) -> Dict[str, Any]:
        """
        Runs ML inference to predict P(accept).
        执行 ML 推断以预测 P(accept)。
        """
        if not self.model:
            return {"ml_score": 0.0, "status": "no_model"}
        
        try:
            if not self._legacy_mode and self.model_payload is not None:
                inference_row = build_decision_inference_feature_row(
                    raw_text,
                    parsed,
                    parser_name=parser_name,
                    validation_context=validation_context,
                    reference_context=reference_context,
                    building_type=building_type,
                    current_decision=current_decision,
                )
                frame = build_decision_inference_frame(
                    inference_row,
                    feature_names=self.feature_names or None,
                )
                probs = self.model.predict_proba(frame)[0]
                pred_raw = self.model.predict(frame)
                ml_decision_idx = int(pred_raw[0][0] if hasattr(pred_raw[0], "__len__") else pred_raw[0])
                ml_decision = (
                    self.present_labels[ml_decision_idx]
                    if 0 <= ml_decision_idx < len(self.present_labels)
                    else "review"
                )
                return {
                    "ml_score": round(float(probs[ml_decision_idx]), 4),
                    "probabilities": {
                        self.present_labels[i]: round(float(probs[i]), 4)
                        for i in range(min(len(probs), len(self.present_labels)))
                    },
                    "status": "success",
                    "ml_decision": ml_decision,
                    "model_type": str(self.metadata.get("model_type") or self.model_payload.get("model_type") or ""),
                }

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
                "ml_decision": ml_decision,
                "model_type": "legacy_catboost_vector",
            }
        except Exception as e:
            logger.error("ML Inference error: %s", e)
            return {"ml_score": 0.0, "status": "error", "error": str(e)}

def get_model_service(manifest: Dict[str, Any] | None = None) -> ModelService:
    """
    Returns a new instance of ModelService.
    返回 ModelService 的新实例。
    """
    return ModelService(manifest=manifest)


def build_model_service_from_manifest(manifest: dict[str, Any] | None) -> ModelService:
    """
    Builds a ModelService instance from a versioned manifest.
    根据版本化的清单构建 ModelService 实例。
    """
    return ModelService(manifest=manifest)
