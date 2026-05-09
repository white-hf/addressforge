import unittest
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestReviewQueueBehavior(unittest.TestCase):
    @patch("addressforge.services.review_service._run_llm_prescreen")
    @patch("addressforge.services.review_service._load_prescreen_cache")
    @patch("addressforge.services.review_service._fetch_cleaning_detail")
    @patch("addressforge.services.review_service.list_active_learning_queue")
    def test_get_review_queue_does_not_block_on_live_llm_prescreen(
        self,
        mock_list_queue,
        mock_fetch_detail,
        mock_load_cache,
        mock_run_llm,
    ):
        from addressforge.services.review_service import get_review_queue

        mock_list_queue.return_value = [
            {
                "queue_id": 1,
                "source_id": 123,
                "source_name": "address_cleaning_result",
                "task_type": "review",
                "priority": 10,
                "confidence": 0.6,
                "reason": "test",
            }
        ]
        mock_fetch_detail.return_value = {
            "raw_address_text": "6957 Mumford Rd. Apt.27, Halifax, NS",
            "decision": "review",
            "reason": "Verification Required",
            "building_type": "single_unit",
            "suggested_unit_number": None,
        }
        mock_load_cache.return_value = None

        rows = get_review_queue("default", limit=10)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["llm_prescreen_status"], "pending")
        self.assertIsNone(rows[0]["llm_prescreen"])
        self.assertIn("pending", rows[0]["llm_advice"].lower())
        mock_run_llm.assert_not_called()

    @patch("addressforge.services.review_service._run_llm_prescreen")
    @patch("addressforge.services.review_service._load_prescreen_cache")
    @patch("addressforge.services.review_service._fetch_cleaning_detail")
    @patch("addressforge.services.review_service.list_active_learning_queue")
    def test_get_review_queue_exposes_structured_fields_for_review_editing(
        self,
        mock_list_queue,
        mock_fetch_detail,
        mock_load_cache,
        mock_run_llm,
    ):
        from addressforge.services.review_service import get_review_queue

        mock_list_queue.return_value = [
            {
                "queue_id": 2,
                "source_id": 456,
                "source_name": "address_cleaning_result",
                "task_type": "review",
                "priority": 10,
                "confidence": 0.4,
                "reason": "test",
            }
        ]
        mock_fetch_detail.return_value = {
            "raw_address_text": "two Heritage Court FALL RIVER NS",
            "decision": "review",
            "reason": "Verification Required",
            "building_type": "single_unit",
            "suggested_unit_number": None,
            "parser_json": '{"best_candidate":{"parsed":{"street_number":"2","street_name":"HERITAGE COURT","city":"FALL RIVER","province":"NS","postal_code":null}}}',
        }
        mock_load_cache.return_value = None

        rows = get_review_queue("default", limit=10)

        self.assertEqual(rows[0]["street_number"], "2")
        self.assertEqual(rows[0]["street_name"], "HERITAGE COURT")
        self.assertEqual(rows[0]["city"], "FALL RIVER")
        self.assertEqual(rows[0]["province"], "NS")
        self.assertIsNone(rows[0]["postal_code"])
        mock_run_llm.assert_not_called()

    @patch("addressforge.services.review_service.db_cursor")
    @patch("addressforge.services.review_service.upsert_gold_label")
    @patch("addressforge.services.review_service._fetch_cleaning_detail")
    @patch("addressforge.services.review_service.fetch_all")
    def test_submit_review_writes_structured_fields_into_gold(
        self,
        mock_fetch_all,
        mock_fetch_detail,
        mock_upsert,
        mock_db_cursor,
    ):
        from addressforge.services.review_service import submit_review

        mock_fetch_all.side_effect = [
            [
                {
                    "queue_id": 7,
                    "workspace_name": "default",
                    "source_id": "456",
                    "task_type": "review",
                    "source_name": "address_cleaning_result",
                    "confidence": 0.4,
                    "reason": "test queue reason",
                }
            ],
            [
                {
                    "decision": "review",
                    "building_type": "single_unit",
                    "suggested_unit_number": None,
                    "reason": "Verification Required",
                }
            ],
        ]
        mock_fetch_detail.return_value = {
            "raw_address_text": "two Heritage Court FALL RIVER NS",
            "parser_json": '{"best_candidate":{"parsed":{"street_number":"2","street_name":"HERITAGE COURT","city":"FALL RIVER","province":"NS","postal_code":null}}}',
        }
        mock_upsert.return_value = {"gold_label_id": 1}
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db_cursor.return_value.__enter__.return_value = (mock_conn, mock_cursor)

        result = submit_review(
            task_id=7,
            decision="correct",
            notes="normalized from number words",
            building_type="single_unit",
            unit_number=None,
            street_number="2",
            street_name="HERITAGE COURT",
            city="FALL RIVER",
            province="NS",
            postal_code=None,
        )

        self.assertEqual(result["status"], "success")
        kwargs = mock_upsert.call_args.kwargs
        self.assertEqual(kwargs["label_json"]["street_number"], "2")
        self.assertEqual(kwargs["label_json"]["street_name"], "HERITAGE COURT")
        self.assertEqual(kwargs["label_json"]["city"], "FALL RIVER")
        self.assertEqual(kwargs["label_json"]["province"], "NS")
        self.assertEqual(kwargs["label_json"]["building_type"], "single_unit")
