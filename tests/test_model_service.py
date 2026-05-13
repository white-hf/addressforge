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


if __name__ == "__main__":
    unittest.main()
