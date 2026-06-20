from __future__ import annotations

import json
import os
import pickle
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from addressforge.services import model_service as model_service_module
from addressforge.services.model_service import ModelService
from addressforge.core.decision_features import build_decision_inference_frame


class DummyEstimator:
    def __init__(self):
        self.last_columns: list[str] = []

    def predict_proba(self, frame):
        self.last_columns = list(frame.columns)
        return np.asarray([[0.2, 0.8]], dtype=float)

    def predict(self, frame):
        self.last_columns = list(frame.columns)
        return np.asarray([[1]], dtype=int)


class TestModelService(unittest.TestCase):
    def tearDown(self):
        ModelService._instance = None
        model_service_module._model_service = None

    def test_predict_decision_uses_metadata_schema_sidecar(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            metadata_path = Path(tmpdir) / "decision.json"
            model_path = Path(tmpdir) / "decision.pkl"
            estimator = DummyEstimator()
            metadata_path.write_text(
                json.dumps(
                    {
                        "model_type": "catboost",
                        "catboost_feature_names": [
                            "confidence",
                            "reference_score",
                            "pattern",
                            "decision_reason",
                        ],
                        "present_labels": ["accept", "reject"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with model_path.open("wb") as fh:
                pickle.dump(
                    {
                        "model_type": "catboost",
                        "estimator": estimator,
                        "feature_names": [
                            "confidence",
                            "reference_score",
                            "pattern",
                            "decision_reason",
                        ],
                        "present_labels": ["accept", "reject"],
                    },
                    fh,
                )

            with patch.dict(
                os.environ,
                {
                    "ADDRESSFORGE_DECISION_MODEL_METADATA_PATH": str(metadata_path),
                    "ADDRESSFORGE_DECISION_MODEL_PKL_PATH": str(model_path),
                    "ADDRESSFORGE_DECISION_MODEL_CBM_PATH": str(Path(tmpdir) / "missing.cbm"),
                },
                clear=False,
            ):
                ModelService._instance = None
                model_service_module._model_service = None
                service = ModelService()
                result = service.predict_decision(
                    "241 Broad Street 105 Bedford NS",
                    {
                        "street_number": "241",
                        "street_name": "BROAD STREET",
                        "unit_number": "105",
                        "unit_source": "trailing_unit",
                        "feature_vector": {
                            "pattern": "bare_trailing_unit_before_city",
                            "has_residential_unit_hint": True,
                        },
                    },
                    parser_name="hybrid",
                    validation_context={
                        "confidence": 0.84,
                        "reason": "Parser confidence is moderate; review is safer.",
                        "hints": {"reference_score": 0.67},
                    },
                    reference_context={"candidates": [{"unit_number": "105"}]},
                    building_type="multi_unit",
                    current_decision="review",
                )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["ml_decision"], "reject")
        self.assertEqual(service.model.last_columns, ["confidence", "reference_score", "pattern", "decision_reason"])
        self.assertEqual(result["probabilities"], {"accept": 0.2, "reject": 0.8})

    def test_build_decision_inference_frame_coerces_categorical_columns(self):
        frame = build_decision_inference_frame(
            {
                "confidence": 0.91,
                "reference_score": 0.42,
                "reference_candidate_count": 3,
                "reference_has_unit_hint": 1,
                "gps_conflict": 0,
                "parser_disagreement": 1,
                "street_number_present": 1,
                "street_name_present": 1,
                "unit_present": 1,
                "explicit_unit_hint": 1,
                "residential_unit_hint": 0,
                "commercial_unit_hint": 0,
                "geographic_modifier_only": 0,
                "double_number_pattern": 0,
                "bare_trailing_unit_city_pattern": 0,
                "numbered_road_name": 0,
                "building_type_multi_unit": 1,
                "building_type_commercial": 0,
                "raw_text_length": 42,
                "pattern": 5.0,
                "unit_source": 7,
                "decision_reason": 2.5,
                "task_type": 1,
                "sample_pool": 9,
            }
        )

        self.assertEqual(frame.iloc[0]["pattern"], "5.0")
        self.assertEqual(frame.iloc[0]["unit_source"], "7")
        self.assertEqual(frame.iloc[0]["decision_reason"], "2.5")
        self.assertEqual(frame.iloc[0]["task_type"], "1")
        self.assertEqual(frame.iloc[0]["sample_pool"], "9")
        self.assertEqual(str(frame.dtypes["pattern"]), "str")
        self.assertEqual(frame.iloc[0]["confidence"], 0.91)
        self.assertEqual(frame.iloc[0]["reference_candidate_count"], 3.0)


if __name__ == "__main__":
    unittest.main()
