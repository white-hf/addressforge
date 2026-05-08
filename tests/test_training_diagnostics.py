from __future__ import annotations

import unittest
from unittest.mock import patch

from addressforge.learning.trainer import (
    _derive_hard_sample_profile,
    _derive_label_consistency_diagnostics,
    _normalize_training_task_type,
    _derive_row_learning_weight,
)


class TestTrainingDiagnostics(unittest.TestCase):
    @patch("addressforge.learning.trainer.fetch_all")
    def test_hard_sample_profile_tracks_balanced_sample_pools(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "source_id": "100",
                "task_type": "review",
                "source_name": "address_cleaning_result",
                "notes": "[sample_pool=calibration_single_unit]",
                "label_json": '{"building_type":"single_unit"}',
                "raw_address_text": "14 Park Street, Trenton, NS, B0K1X0",
            },
            {
                "source_id": "200",
                "task_type": "building_type",
                "source_name": "address_cleaning_result",
                "notes": "[sample_pool=calibration_multi_unit]",
                "label_json": '{"building_type":"multi_unit"}',
                "raw_address_text": "128 Highbury Rd Apt 2 New Minas NS",
            },
            {
                "source_id": "300",
                "task_type": "unit_number",
                "source_name": "address_cleaning_result",
                "notes": "[sample_pool=unit_boost]",
                "label_json": '{"building_type":"multi_unit"}',
                "raw_address_text": "1119 Tower Rd unit 706 Tower Road Halifax NS",
            },
            {
                "source_id": "400",
                "task_type": "building_type",
                "source_name": "address_cleaning_result",
                "notes": "[sample_pool=hard_correction]",
                "label_json": '{"building_type":"single_unit"}',
                "raw_address_text": "194 Union St 1676 PICTOU NS",
            },
        ]

        profile = _derive_hard_sample_profile("default")
        self.assertEqual(profile["sample_pool_counts"]["calibration_single_unit"], 1)
        self.assertEqual(profile["sample_pool_counts"]["calibration_multi_unit"], 1)
        self.assertEqual(profile["sample_pool_counts"]["unit_boost"], 1)
        self.assertEqual(profile["sample_pool_counts"]["hard_correction"], 1)
        self.assertEqual(profile["calibration_pool_gold"], 2)
        self.assertEqual(profile["correction_pool_gold"], 2)
        self.assertAlmostEqual(profile["sample_pool_weight_totals"]["calibration_single_unit"], 1.0)
        self.assertAlmostEqual(profile["sample_pool_weight_totals"]["calibration_multi_unit"], 1.0)
        self.assertAlmostEqual(profile["sample_pool_weight_totals"]["unit_boost"], 0.95)
        self.assertAlmostEqual(profile["sample_pool_weight_totals"]["hard_correction"], 0.7)
        self.assertAlmostEqual(profile["effective_training_weight_total"], 3.65)

    @patch("addressforge.learning.trainer.fetch_all")
    def test_label_consistency_diagnostics_detects_single_unit_with_strong_unit_hint(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "source_id": "132",
                "task_type": "building_type",
                "source_name": "address_cleaning_result",
                "notes": None,
                "label_json": '{"building_type":"single_unit"}',
                "raw_address_text": "128 Highbury Rd Apt 2 New Minas NS",
            },
            {
                "source_id": "906",
                "task_type": "unit_number",
                "source_name": "address_cleaning_result",
                "notes": None,
                "label_json": '{"building_type":"single_unit"}',
                "raw_address_text": "48 Rudolf Road, Upper Lahave, NS, B4V7B7",
            },
            {
                "source_id": "700",
                "task_type": "building_type",
                "source_name": "address_cleaning_result",
                "notes": None,
                "label_json": '{"building_type":"commercial"}',
                "raw_address_text": "Upper Unit 5, Halifax, NS",
            },
        ]

        diagnostics = _derive_label_consistency_diagnostics("default", example_limit=10)
        self.assertEqual(diagnostics["single_unit_with_strong_unit_hint_count"], 1)
        self.assertEqual(diagnostics["single_unit_with_strong_unit_hint_examples"][0]["source_id"], "132")
        self.assertEqual(diagnostics["commercial_with_residential_pattern_count"], 1)
        self.assertEqual(
            diagnostics["commercial_with_residential_pattern_examples"][0]["source_id"],
            "700",
        )

    def test_row_learning_weight_downweights_legacy_review_bias_but_keeps_true_multi_unit_positive(self):
        legacy_double_number_review = {
            "task_type": "review",
            "source_name": "address_cleaning_result",
            "notes": None,
            "raw_address_text": "194 Union St 1676 PICTOU NS",
        }
        legacy_multi_unit_positive = {
            "task_type": "review",
            "source_name": "address_cleaning_result",
            "notes": None,
            "raw_address_text": "1119 Tower Rd Unit 706 Halifax NS",
        }

        negative_weight = _derive_row_learning_weight(
            legacy_double_number_review,
            {"building_type": "single_unit"},
        )
        positive_weight = _derive_row_learning_weight(
            legacy_multi_unit_positive,
            {"building_type": "multi_unit"},
        )

        self.assertLess(negative_weight, positive_weight)
        self.assertLessEqual(negative_weight, 0.5)
        self.assertGreaterEqual(positive_weight, 0.95)

    def test_normalize_training_task_type_maps_legacy_pool_labels_to_review(self):
        self.assertEqual(_normalize_training_task_type("calibration_accept", ""), "review")
        self.assertEqual(_normalize_training_task_type("unit_boost_pending", ""), "review")
        self.assertEqual(_normalize_training_task_type("hard_correction_accept", ""), "review")
        self.assertEqual(
            _normalize_training_task_type("anything_else", "[sample_pool=calibration_single_unit]"),
            "review",
        )

    @patch("addressforge.learning.trainer.fetch_all")
    def test_hard_sample_profile_normalizes_legacy_task_type_labels(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "source_id": "100",
                "task_type": "calibration_accept",
                "source_name": "address_cleaning_result",
                "notes": None,
                "label_json": '{"building_type":"single_unit"}',
                "raw_address_text": "14 Park Street, Trenton, NS, B0K1X0",
            },
            {
                "source_id": "200",
                "task_type": "unit_boost_accept",
                "source_name": "address_cleaning_result",
                "notes": None,
                "label_json": '{"building_type":"multi_unit"}',
                "raw_address_text": "241 Broad Street 105 Bedford NS",
            },
        ]

        profile = _derive_hard_sample_profile("default")
        self.assertEqual(profile["task_type_counts"]["review"], 2)


if __name__ == "__main__":
    unittest.main()
