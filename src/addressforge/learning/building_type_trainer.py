from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from catboost import CatBoostClassifier

from addressforge.core.common import (
    create_run,
    dumps_payload,
    fetch_all,
    finish_run,
)
from addressforge.core.config import ADDRESSFORGE_MODEL_ARTIFACT_DIR, ADDRESSFORGE_WORKSPACE_NAME
from addressforge.core.features import AddressFeatureExtractor
from addressforge.core.utils import logger

class BuildingTypeTrainer:
    """
    Trains a model to classify building types (single_unit, multi_unit, commercial).
    """

    def __init__(self, workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME):
        self.workspace_name = workspace_name
        self.extractor = AddressFeatureExtractor()

    def collect_training_samples(self, limit: int = 2000) -> List[Dict[str, Any]]:
        query = """
            SELECT 
                g.label_json as gold_json,
                r.raw_address_text,
                c.parser_json,
                c.validation_json,
                c.reference_json
            FROM gold_label g
            JOIN raw_address_record r ON g.source_id = CAST(r.raw_id AS CHAR)
            JOIN address_cleaning_result c ON r.raw_id = c.raw_id
            WHERE g.workspace_name = %s
              AND g.review_status = 'accepted'
              AND g.source_id REGEXP '^[0-9]+$'
            LIMIT %s
        """
        rows = fetch_all(query, (self.workspace_name, limit))
        
        # Class mapping
        class_map = {"single_unit": 0, "multi_unit": 1, "commercial": 2}
        dataset = []
        
        for row in rows:
            raw_text = row["raw_address_text"]
            gold_json = json.loads(row["gold_json"]) if isinstance(row["gold_json"], str) else row["gold_json"]
            
            building_type = gold_json.get("building_type")
            if building_type not in class_map:
                continue
                
            parser_json = json.loads(row["parser_json"]) if row.get("parser_json") else {}
            parsed = parser_json.get("best_candidate", {}).get("parsed", {})
            
            validation_ctx = json.loads(row["validation_json"]) if row.get("validation_json") else {}
            reference_ctx = json.loads(row["reference_json"]) if row.get("reference_json") else {}
            semantic_alignment = 1.0 if reference_ctx.get("external_id") else 0.0

            features = self.extractor.extract_features(
                raw_text, 
                parsed, 
                parser_name="hybrid",
                validation_context=validation_ctx,
                reference_context=reference_ctx,
                semantic_alignment=semantic_alignment
            )
            dataset.append({
                "features": self.extractor.vectorize(features),
                "label": class_map[building_type]
            })
        return dataset

    def train_building_type_model(self, model_version: str | None = None) -> Dict[str, Any]:
        run_id = create_run("ml_train", notes="BuildingType classification training")
        try:
            dataset = self.collect_training_samples()
            if not dataset:
                return {"status": "skipped", "reason": "no_data"}

            X = pd.DataFrame([d["features"] for d in dataset])
            y = pd.Series([d["label"] for d in dataset])

            model = CatBoostClassifier(
                iterations=500,
                depth=6,
                learning_rate=0.08,
                loss_function='MultiClass',
                verbose=False,
                random_seed=42,
                auto_class_weights='Balanced'
            )
            model.fit(X, y)

            version = model_version or f"building_type_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            artifact_dir = Path(ADDRESSFORGE_MODEL_ARTIFACT_DIR)
            artifact_dir.mkdir(parents=True, exist_ok=True)
            model_path = artifact_dir / f"{version}.cbm"
            model.save_model(str(model_path))

            result = {
                "model_type": "catboost_multiclass",
                "model_path": str(model_path),
                "model_version": version,
                "sample_count": len(dataset),
                "label_distribution": y.value_counts().to_dict()
            }
            finish_run(run_id, "completed", notes=dumps_payload(result))
            return result
        except Exception as e:
            finish_run(run_id, "failed", notes=str(e))
            raise
