from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from catboost import CatBoostClassifier

from addressforge.core.common import (
    canonicalize_unit_number,
    create_run,
    db_cursor,
    dumps_payload,
    fetch_all,
    finish_run,
    normalize_street_name,
)
from addressforge.core.config import ADDRESSFORGE_MODEL_ARTIFACT_DIR, ADDRESSFORGE_WORKSPACE_NAME
from addressforge.core.features import AddressFeatureExtractor
from addressforge.core.utils import logger


class ParserRerankerTrainer:
    """
    Trains a calibration model to rank and select the best parser output.
    训练一个校准模型，用于对解析器输出进行排序和筛选。
    """

    def __init__(self, workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME):
        self.workspace_name = workspace_name
        self.extractor = AddressFeatureExtractor()

    def collect_training_pairs(self, limit: int = 2000) -> List[Dict[str, Any]]:
        """
        Collects candidate pairs and features for supervision.
        收集用于监督的候选对和特征。
        """
        query = """
            SELECT
                g.label_json as gold_json,
                acr.parser_json,
                acr.validation_json,
                r.raw_address_text
            FROM gold_label g
            JOIN (
                SELECT source_id, MAX(gold_label_id) AS latest_gold_label_id
                FROM gold_label
                WHERE workspace_name = %s
                  AND review_status = 'accepted'
                  AND label_source = 'human'
                GROUP BY source_id
            ) latest
              ON latest.latest_gold_label_id = g.gold_label_id
            JOIN address_cleaning_result acr
              ON g.workspace_name = acr.workspace_name
             AND CAST(acr.raw_id AS CHAR) = g.source_id
            JOIN raw_address_record r
              ON acr.workspace_name = r.workspace_name
              AND acr.raw_id = r.raw_id
            WHERE g.workspace_name = %s
              AND g.review_status = 'accepted'
              AND g.label_source = 'human'
            LIMIT %s
        """
        rows = fetch_all(query, (self.workspace_name, self.workspace_name, limit))

        dataset = []
        for row in rows:
            raw_text = row["raw_address_text"]
            gold_json = json.loads(row["gold_json"]) if isinstance(row["gold_json"], str) else row["gold_json"]
            parser_json = json.loads(row["parser_json"]) if isinstance(row["parser_json"], str) else row["parser_json"]
            
            candidates = parser_json.get("candidates", [])
            if not candidates:
                continue

            gold_sn = str(gold_json.get("street_number") or "").strip()
            gold_st = normalize_street_name(gold_json.get("street_name"))
            gold_un = canonicalize_unit_number(gold_json.get("unit_number"))
            gold_base_key = gold_json.get("base_address_key")

            best_h_score = max([float(c.get("score") or 0.5) for c in candidates])

            for cand in candidates:
                parsed = cand.get("parsed", {})
                cand_sn = str(parsed.get("street_number") or "").strip()
                cand_st = normalize_street_name(parsed.get("street_name"))
                cand_un = canonicalize_unit_number(parsed.get("unit_number"))
                cand_base_key = parsed.get("base_address_key")

                is_match = (cand_sn == gold_sn and cand_st == gold_st and cand_un == gold_un)
                semantic_alignment = 1.0 if gold_base_key and cand_base_key and gold_base_key == cand_base_key else 0.0

                features = self.extractor.extract_features(
                    raw_text,
                    parsed,
                    parser_name=cand.get("parser_name", "unknown"),
                    best_candidate_score=best_h_score,
                    semantic_alignment=semantic_alignment
                )
                dataset.append({
                    "features": self.extractor.vectorize(features),
                    "label": 1 if is_match else 0
                })
        return dataset

    def train_reranker_model(self, model_version: str | None = None) -> Dict[str, Any]:
        """
        Trains a CatBoost reranker model.
        """
        run_id = create_run("ml_train", notes="Supervised Reranker training")
        try:
            dataset = self.collect_training_pairs()
            if not dataset:
                return {"status": "skipped", "reason": "no_data"}

            X = pd.DataFrame([d["features"] for d in dataset])
            y = pd.Series([d["label"] for d in dataset])

            model = CatBoostClassifier(
                iterations=500,
                depth=6,
                learning_rate=0.05,
                loss_function='Logloss',
                verbose=False,
                random_seed=42,
                auto_class_weights='Balanced'
            )
            model.fit(X, y)

            version = model_version or f"reranker_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            artifact_dir = Path(ADDRESSFORGE_MODEL_ARTIFACT_DIR)
            artifact_dir.mkdir(parents=True, exist_ok=True)
            model_path = artifact_dir / f"{version}.cbm"
            model.save_model(str(model_path))

            result = {
                "model_type": "catboost",
                "model_path": str(model_path),
                "model_version": version,
                "sample_count": len(dataset),
                "positive_count": int(sum(y))
            }
            finish_run(run_id, "completed", notes=dumps_payload(result))
            return result
        except Exception as e:
            finish_run(run_id, "failed", notes=str(e))
            raise
