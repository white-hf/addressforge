import unittest
from unittest.mock import patch

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

