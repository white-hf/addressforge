from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from addressforge.learning.gold import (
    _looks_like_decision_calibration_single_unit_candidate,
    _looks_like_residential_unit_relabel_candidate,
    _looks_like_semantic_ambiguity_candidate,
    seed_decision_calibration_review_queue,
    seed_decision_minority_label_review_queue,
    seed_active_learning_queue,
)

class TestGoldSampling(unittest.TestCase):
    """
    Unit tests for the stratified sampling and gold expansion logic.
    针对分层采样与金标扩样逻辑的单元测试。
    """

    @patch("addressforge.learning.gold.fetch_all")
    @patch("addressforge.learning.gold.db_cursor")
    @patch("addressforge.learning.gold.create_run", return_value=99)
    @patch("addressforge.learning.gold.finish_run")
    @patch("addressforge.learning.gold._existing_reviewed_or_queued_source_ids", return_value=set())
    def test_stratified_sampling_distribution(self, mock_existing, mock_finish, mock_create, mock_db, mock_fetch):
        """
        Verifies that balanced sampling creates semantic review tasks and carries pool reasons.
        验证平衡抽样会生成语义正确的审核任务，并携带样本池原因。
        """
        mock_fetch.side_effect = [
            [
                {
                    "raw_id": 101,
                    "decision": "accept",
                    "confidence": 0.95,
                    "reason": "stable house sample",
                    "building_type": "single_unit",
                    "raw_address_text": "14 Park Street, Trenton, NS, B0K1X0",
                    "suggested_unit_number": None,
                    "feature_flags": {"has_double_number": False},
                }
            ],
            [
                {
                    "raw_id": 201,
                    "decision": "accept",
                    "confidence": 0.91,
                    "reason": "stable apartment sample",
                    "building_type": "multi_unit",
                    "raw_address_text": "128 Highbury Rd Apt 2 New Minas NS",
                    "suggested_unit_number": "2",
                    "feature_flags": {"has_double_number": False},
                }
            ],
            [
                {
                    "raw_id": 301,
                    "decision": "review",
                    "confidence": 0.40,
                    "reason": "apartment recall candidate",
                    "building_type": "multi_unit",
                    "raw_address_text": "1119 Tower Rd unit 706 Tower Road Halifax NS",
                    "suggested_unit_number": "706",
                    "feature_flags": {"has_double_number": False},
                }
            ],
            [
                {
                    "raw_id": 401,
                    "decision": "review",
                    "confidence": 0.30,
                    "reason": "double-number boundary sample",
                    "building_type": "single_unit",
                    "raw_address_text": "194 Union St 1676 PICTOU NS",
                    "suggested_unit_number": None,
                    "feature_flags": {"has_double_number": True},
                }
            ],
        ]

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.return_value.__enter__.return_value = (mock_conn, mock_cursor)

        result = seed_active_learning_queue(workspace_name="default", limit=10)

        self.assertEqual(result["inserted"], 4)
        self.assertEqual(mock_fetch.call_count, 4)
        self.assertEqual(
            result["breakdown"],
            {
                "calibration_single_unit": 1,
                "calibration_multi_unit": 1,
                "unit_boost": 1,
                "hard_correction": 1,
            },
        )

        insert_calls = [
            call for call in mock_cursor.execute.call_args_list
            if "INSERT INTO active_learning_queue" in call.args[0]
        ]
        self.assertEqual(len(insert_calls), 4)
        self.assertTrue(all("feature_flags" not in call.args[0] for call in insert_calls))
        inserted_task_types = [call.args[1][2] for call in insert_calls]
        self.assertEqual(inserted_task_types, ["review", "building_type", "unit_number", "building_type"])
        inserted_reasons = [call.args[1][5] for call in insert_calls]
        self.assertTrue(any("Balanced pool: calibration_single_unit" in reason for reason in inserted_reasons))
        self.assertTrue(any("Balanced pool: calibration_multi_unit" in reason for reason in inserted_reasons))
        self.assertTrue(any("Balanced pool: unit_boost" in reason for reason in inserted_reasons))
        self.assertTrue(any("Balanced pool: hard_correction" in reason for reason in inserted_reasons))

    def test_relabel_candidate_detector_accepts_strong_unit_hints(self):
        self.assertTrue(
            _looks_like_residential_unit_relabel_candidate(
                "128 Highbury Rd Apt 2 New Minas NS",
                "single_unit",
            )
        )
        self.assertTrue(
            _looks_like_residential_unit_relabel_candidate(
                "Unit 5 - 115 Highbury Rd, New Minas, NS, B4N3P9, CA",
                "single_unit",
            )
        )

    def test_relabel_candidate_detector_rejects_geographic_upper_lower_noise(self):
        self.assertFalse(
            _looks_like_residential_unit_relabel_candidate(
                "48 Rudolf Road, Upper Lahave, NS, B4V7B7",
                "single_unit",
            )
        )
        self.assertFalse(
            _looks_like_residential_unit_relabel_candidate(
                "881 Middle Dyke Rd, Upper Canard, NS, B0P1J0, CA",
                "single_unit",
            )
        )

    def test_semantic_ambiguity_detector_handles_geographic_vs_true_unit_cases(self):
        self.assertFalse(
            _looks_like_semantic_ambiguity_candidate(
                "48 Rudolf Road, Upper Lahave, NS, B4V7B7",
                "single_unit",
                None,
            )
        )

    def test_decision_calibration_detector_accepts_clean_single_unit_review_cases(self):
        self.assertTrue(
            _looks_like_decision_calibration_single_unit_candidate(
                "N/A 11 EAGLE RD, Bible Hill, NS",
                "single_unit",
                "review",
                None,
            )
        )
        self.assertTrue(
            _looks_like_decision_calibration_single_unit_candidate(
                "Terrace Street 264 New Glasgow NS",
                "single_unit",
                "review",
                None,
            )
        )

    def test_decision_calibration_detector_rejects_unit_like_or_non_review_cases(self):
        self.assertFalse(
            _looks_like_decision_calibration_single_unit_candidate(
                "241 Broad Street 105 Bedford NS",
                "single_unit",
                "review",
                "105",
            )
        )
        self.assertFalse(
            _looks_like_decision_calibration_single_unit_candidate(
                "137 Mackay St STELLARTON",
                "single_unit",
                "accept",
                None,
            )
        )

    @patch("addressforge.learning.gold.fetch_all")
    @patch("addressforge.learning.gold.db_cursor")
    @patch("addressforge.learning.gold.create_run", return_value=199)
    @patch("addressforge.learning.gold.finish_run")
    @patch("addressforge.learning.gold._existing_reviewed_or_queued_source_ids", return_value=set())
    def test_seed_decision_calibration_review_queue(self, mock_existing, mock_finish, mock_create, mock_db, mock_fetch):
        mock_fetch.side_effect = [
            [
                {
                    "metrics_json": "{\"decision_errors\":[{\"source_id\":\"501\",\"bucket\":\"OVER_SENSITIVE_REVIEW\",\"predicted\":\"review\",\"raw_text\":\"N/A 11 EAGLE RD, Bible Hill, NS\",\"building_type\":\"single_unit\"}]}"
                }
            ],
            [
                {
                    "raw_id": 601,
                    "decision": "review",
                    "confidence": 0.71,
                    "reason": "parser disagreement but complete single-unit street",
                    "building_type": "single_unit",
                    "raw_address_text": "Terrace Street 264 New Glasgow NS",
                    "suggested_unit_number": None,
                }
            ],
        ]
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.return_value.__enter__.return_value = (mock_conn, mock_cursor)

        result = seed_decision_calibration_review_queue(workspace_name="default", limit=10)

        self.assertEqual(result["inserted"], 2)
        insert_calls = [
            call for call in mock_cursor.execute.call_args_list
            if "INSERT INTO active_learning_queue" in call.args[0]
        ]
        self.assertEqual(len(insert_calls), 2)
        self.assertTrue(all(call.args[1][3] == "review" for call in insert_calls))
        inserted_reasons = [call.args[1][6] for call in insert_calls]
        self.assertTrue(any("Decision calibration" in reason for reason in inserted_reasons))

    @patch("addressforge.learning.gold.fetch_all")
    @patch("addressforge.learning.gold.db_cursor")
    @patch("addressforge.learning.gold.create_run", return_value=299)
    @patch("addressforge.learning.gold.finish_run")
    @patch("addressforge.learning.gold._existing_reviewed_or_queued_source_ids", return_value=set())
    @patch("addressforge.learning.gold._existing_reviewed_or_queued_text_keys", return_value=set())
    def test_seed_decision_minority_label_review_queue(
        self,
        mock_text_keys,
        mock_existing,
        mock_finish,
        mock_create,
        mock_db,
        mock_fetch,
    ):
        mock_fetch.side_effect = [
            [
                {
                    "raw_id": 703,
                    "decision": "reject",
                    "confidence": 0.12,
                    "reason": "Address is too incomplete to parse safely.",
                    "building_type": "",
                    "raw_address_text": "UNKNOWN LOT NS",
                    "suggested_unit_number": None,
                }
            ],
            [
                {
                    "raw_id": 701,
                    "decision": "review",
                    "confidence": 0.41,
                    "reason": "Address is incomplete and needs manual confirmation.",
                    "building_type": "single_unit",
                    "raw_address_text": "N/A 11 EAGLE RD, Bible Hill, NS",
                    "suggested_unit_number": None,
                }
            ],
            [
                {
                    "raw_id": 702,
                    "decision": "review",
                    "confidence": 0.55,
                    "reason": "Commercial-looking address parsed well, but unit details may need confirmation.",
                    "building_type": "commercial",
                    "raw_address_text": "University of Kings College6350 COBURG ROAD HALIFAX NS",
                    "suggested_unit_number": None,
                }
            ],
            [],
            [],
        ]
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.return_value.__enter__.return_value = (mock_conn, mock_cursor)

        result = seed_decision_minority_label_review_queue(workspace_name="default", limit=10)

        self.assertEqual(result["inserted"], 3)
        self.assertEqual(result["bucket_counts"]["decision_reject_candidate"], 1)
        self.assertEqual(result["bucket_counts"]["decision_review_incomplete"], 1)
        self.assertEqual(result["bucket_counts"]["decision_review_commercial"], 1)

        insert_calls = [
            call for call in mock_cursor.execute.call_args_list
            if "INSERT INTO active_learning_queue" in call.args[0]
        ]
        self.assertEqual(len(insert_calls), 3)
        inserted_reasons = [call.args[1][6] for call in insert_calls]
        self.assertTrue(any("decision_reject_candidate" in reason for reason in inserted_reasons))
        self.assertTrue(any("decision_review_incomplete" in reason for reason in inserted_reasons))
        self.assertTrue(any("decision_review_commercial" in reason for reason in inserted_reasons))
        self.assertTrue(
            _looks_like_semantic_ambiguity_candidate(
                "Upper 123 Main St, Halifax, NS",
                "multi_unit",
                "UPPER",
            )
        )
        self.assertTrue(
            _looks_like_semantic_ambiguity_candidate(
                "128 Highbury Rd Apt 2 New Minas NS",
                "single_unit",
                None,
            )
        )

    @patch("addressforge.learning.gold.fetch_all")
    @patch("addressforge.learning.gold.db_cursor")
    @patch("addressforge.learning.gold.create_run", return_value=399)
    @patch("addressforge.learning.gold.finish_run")
    @patch(
        "addressforge.learning.gold._existing_reviewed_or_queued_source_ids",
        return_value={"701", "702", "703"},
    )
    @patch("addressforge.learning.gold._existing_reviewed_or_queued_text_keys", return_value=set())
    def test_seed_decision_minority_label_skips_existing_before_limit(self, mock_text_keys, mock_existing, mock_finish, mock_create, mock_db, mock_fetch):
        mock_fetch.side_effect = [
            [
                {
                    "raw_id": 703,
                    "decision": "reject",
                    "confidence": 0.12,
                    "reason": "Address is too incomplete to parse safely.",
                    "building_type": "",
                    "raw_address_text": "UNKNOWN LOT NS",
                    "suggested_unit_number": None,
                },
                {
                    "raw_id": 704,
                    "decision": "reject",
                    "confidence": 0.18,
                    "reason": "Address is too incomplete to parse safely.",
                    "building_type": "",
                    "raw_address_text": "UNKNOWN LOT 2 NS",
                    "suggested_unit_number": None,
                },
            ],
            [
                {
                    "raw_id": 701,
                    "decision": "review",
                    "confidence": 0.41,
                    "reason": "Address is incomplete and needs manual confirmation.",
                    "building_type": "single_unit",
                    "raw_address_text": "N/A 11 EAGLE RD, Bible Hill, NS",
                    "suggested_unit_number": None,
                },
                {
                    "raw_id": 705,
                    "decision": "review",
                    "confidence": 0.44,
                    "reason": "Address is incomplete and needs manual confirmation.",
                    "building_type": "single_unit",
                    "raw_address_text": "N/A 15 EAGLE RD, Bible Hill, NS",
                    "suggested_unit_number": None,
                },
            ],
            [
                {
                    "raw_id": 702,
                    "decision": "review",
                    "confidence": 0.55,
                    "reason": "Commercial-looking address parsed well, but unit details may need confirmation.",
                    "building_type": "commercial",
                    "raw_address_text": "University of Kings College6350 COBURG ROAD HALIFAX NS",
                    "suggested_unit_number": None,
                }
            ],
            [],
            [],
        ]
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.return_value.__enter__.return_value = (mock_conn, mock_cursor)

        result = seed_decision_minority_label_review_queue(workspace_name="default", limit=2)

        self.assertEqual(result["inserted"], 2)
        insert_calls = [
            call for call in mock_cursor.execute.call_args_list
            if "INSERT INTO active_learning_queue" in call.args[0]
        ]
        inserted_source_ids = [call.args[1][2] for call in insert_calls]
        self.assertEqual(inserted_source_ids, ["704", "705"])

    @patch("addressforge.learning.gold.fetch_all")
    @patch("addressforge.learning.gold.db_cursor")
    @patch("addressforge.learning.gold.create_run", return_value=499)
    @patch("addressforge.learning.gold.finish_run")
    @patch("addressforge.learning.gold._existing_reviewed_or_queued_source_ids", return_value=set())
    @patch("addressforge.learning.gold._existing_reviewed_or_queued_text_keys", return_value=set())
    def test_seed_decision_minority_label_dedupes_duplicate_address_text(self, mock_text_keys, mock_existing, mock_finish, mock_create, mock_db, mock_fetch):
        mock_fetch.side_effect = [
            [],
            [
                {
                    "raw_id": 801,
                    "decision": "review",
                    "confidence": 0.41,
                    "reason": "Address is incomplete and needs manual confirmation.",
                    "building_type": "single_unit",
                    "raw_address_text": "Mountain view road coldbrook 2738",
                    "suggested_unit_number": None,
                },
                {
                    "raw_id": 802,
                    "decision": "review",
                    "confidence": 0.42,
                    "reason": "Address is incomplete and needs manual confirmation.",
                    "building_type": "single_unit",
                    "raw_address_text": "Mountain view road coldbrook 2738",
                    "suggested_unit_number": None,
                },
            ],
            [],
            [],
            [],
        ]
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.return_value.__enter__.return_value = (mock_conn, mock_cursor)

        result = seed_decision_minority_label_review_queue(workspace_name="default", limit=10)

        self.assertEqual(result["inserted"], 1)
        insert_calls = [
            call for call in mock_cursor.execute.call_args_list
            if "INSERT INTO active_learning_queue" in call.args[0]
        ]
        self.assertEqual(len(insert_calls), 1)
        self.assertEqual(insert_calls[0].args[1][2], "801")

if __name__ == "__main__":
    unittest.main()
