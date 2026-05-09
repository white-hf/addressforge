from __future__ import annotations

import unittest

from addressforge.learning.supervised_baseline import (
    _extract_decision_training_feature_row,
    _predict_with_softmax_model,
    _train_softmax_baseline,
    _vectorize_dataset,
    run_decision_baseline_pipeline,
    summarize_decision_training_dataset_balance,
)
from unittest.mock import patch


class TestSupervisedBaseline(unittest.TestCase):
    def test_extract_decision_training_feature_row_uses_runtime_signals(self):
        row = {
            "source_id": "42",
            "label_json": '{"decision":"accept","building_type":"multi_unit"}',
            "task_type": "calibration_accept",
            "notes": "[sample_pool=calibration_multi_unit]",
            "raw_address_text": "241 Broad Street 105 Bedford NS",
            "building_type": "multi_unit",
            "validation_json": '{"confidence":0.84,"reason":"Parser confidence is moderate; review is safer.","hints":{"reference_score":0.67,"parser_disagreement":true,"gps_conflict":false}}',
            "parser_json": '{"best_candidate":{"parsed":{"street_number":"241","street_name":"BROAD STREET","unit_number":"105","unit_source":"trailing_unit","feature_vector":{"pattern":"bare_trailing_unit_before_city","has_explicit_unit_hint":false,"has_residential_unit_hint":true,"has_commercial_unit_hint":false,"has_geographic_modifier_only":false,"has_double_number_pattern":true,"has_bare_trailing_unit_city_pattern":true,"is_numbered_road_name":false}}}}',
            "reference_json": '{"candidates":[{"unit_number":"105"}]}',
        }

        features = _extract_decision_training_feature_row(row)
        self.assertIsNotNone(features)
        assert features is not None
        self.assertEqual(features["label"], "accept")
        self.assertEqual(features["task_type"], "review")
        self.assertEqual(features["sample_pool"], "calibration_multi_unit")
        self.assertEqual(features["pattern"], "bare_trailing_unit_before_city")
        self.assertEqual(features["unit_source"], "trailing_unit")
        self.assertEqual(features["unit_present"], 1.0)
        self.assertEqual(features["reference_has_unit_hint"], 1.0)
        self.assertEqual(features["building_type_multi_unit"], 1.0)
        self.assertEqual(features["parser_disagreement"], 1.0)

    def test_vectorize_dataset_encodes_numeric_and_categorical_features(self):
        rows = [
            {
                "label": "accept",
                "pattern": "bare_trailing_unit_before_city",
                "unit_source": "trailing_unit",
                "decision_reason": "moderate confidence",
                "task_type": "review",
                "sample_pool": "calibration_multi_unit",
                "confidence": 0.84,
                "reference_score": 0.67,
                "reference_candidate_count": 1.0,
                "reference_has_unit_hint": 1.0,
                "gps_conflict": 0.0,
                "parser_disagreement": 1.0,
                "street_number_present": 1.0,
                "street_name_present": 1.0,
                "unit_present": 1.0,
                "explicit_unit_hint": 0.0,
                "residential_unit_hint": 1.0,
                "commercial_unit_hint": 0.0,
                "geographic_modifier_only": 0.0,
                "double_number_pattern": 1.0,
                "bare_trailing_unit_city_pattern": 1.0,
                "numbered_road_name": 0.0,
                "building_type_multi_unit": 1.0,
                "building_type_commercial": 0.0,
                "raw_text_length": 29.0,
            },
            {
                "label": "review",
                "pattern": "numbered_road_name",
                "unit_source": "",
                "decision_reason": "low confidence",
                "task_type": "review",
                "sample_pool": "hard_correction",
                "confidence": 0.51,
                "reference_score": 0.0,
                "reference_candidate_count": 0.0,
                "reference_has_unit_hint": 0.0,
                "gps_conflict": 0.0,
                "parser_disagreement": 0.0,
                "street_number_present": 1.0,
                "street_name_present": 1.0,
                "unit_present": 0.0,
                "explicit_unit_hint": 0.0,
                "residential_unit_hint": 0.0,
                "commercial_unit_hint": 0.0,
                "geographic_modifier_only": 0.0,
                "double_number_pattern": 1.0,
                "bare_trailing_unit_city_pattern": 0.0,
                "numbered_road_name": 1.0,
                "building_type_multi_unit": 0.0,
                "building_type_commercial": 0.0,
                "raw_text_length": 31.0,
            },
        ]

        matrix, labels, feature_names, categorical_values = _vectorize_dataset(rows)
        self.assertEqual(matrix.shape[0], 2)
        self.assertEqual(labels.tolist(), [0, 1])
        self.assertIn("confidence", feature_names)
        self.assertIn("pattern=bare_trailing_unit_before_city", feature_names)
        self.assertIn("pattern=numbered_road_name", feature_names)
        self.assertEqual(categorical_values["sample_pool"], ["calibration_multi_unit", "hard_correction"])

    def test_softmax_baseline_learns_simple_signal(self):
        X_train = __import__("numpy").array(
            [
                [1.0, 0.0],
                [0.9, 0.1],
                [0.0, 1.0],
                [0.1, 0.9],
                [0.6, 0.6],
                [0.5, 0.7],
            ],
            dtype=float,
        )
        y_train = __import__("numpy").array([0, 0, 1, 1, 2, 2], dtype=int)

        model = _train_softmax_baseline(X_train, y_train, class_count=3)
        preds = _predict_with_softmax_model(model, X_train)
        self.assertEqual(model["model_type"], "softmax_regression")
        self.assertGreaterEqual(float((preds == y_train).mean()), 0.83)

    @patch("addressforge.learning.supervised_baseline.collect_decision_training_dataset")
    def test_balance_summary_flags_extreme_label_skew(self, mock_collect):
        mock_collect.return_value = [
            {"label": "accept", "task_type": "review", "sample_pool": "calibration_single_unit"},
            {"label": "accept", "task_type": "review", "sample_pool": "calibration_single_unit"},
            {"label": "accept", "task_type": "review", "sample_pool": "calibration_single_unit"},
            {"label": "review", "task_type": "review", "sample_pool": "hard_correction"},
        ]
        summary = summarize_decision_training_dataset_balance("default", artifact_name="decision_balance_test")
        self.assertEqual(summary["label_counts"]["accept"], 3)
        self.assertEqual(summary["label_counts"]["review"], 1)
        self.assertIn("review_label_count_is_low", summary["warnings"])
        self.assertIn("reject_label_count_is_zero", summary["warnings"])

    @patch("addressforge.learning.supervised_baseline.compare_decision_baseline_against_current")
    @patch("addressforge.learning.supervised_baseline.train_decision_baseline")
    @patch("addressforge.learning.supervised_baseline.export_decision_training_dataset")
    @patch("addressforge.learning.supervised_baseline.summarize_decision_training_dataset_balance")
    def test_run_decision_baseline_pipeline_aggregates_steps(
        self,
        mock_balance,
        mock_dataset,
        mock_train,
        mock_compare,
    ):
        mock_balance.return_value = {"artifact_path": "balance.json", "warnings": ["review_label_count_is_low"]}
        mock_dataset.return_value = {"artifact_path": "dataset.json", "sample_count": 10}
        mock_train.return_value = {"metadata_path": "train.json", "metrics": {"eval_macro_f1": 0.5}}
        mock_compare.return_value = {"artifact_path": "compare.json", "model_macro_f1": 0.77}

        result = run_decision_baseline_pipeline("default", model_version="v_test")

        self.assertEqual(result["workspace_name"], "default")
        self.assertEqual(result["model_version"], "v_test")
        self.assertEqual(result["balance"]["artifact_path"], "balance.json")
        self.assertEqual(result["dataset"]["artifact_path"], "dataset.json")
        self.assertEqual(result["training"]["metadata_path"], "train.json")
        self.assertEqual(result["comparison"]["artifact_path"], "compare.json")


if __name__ == "__main__":
    unittest.main()
