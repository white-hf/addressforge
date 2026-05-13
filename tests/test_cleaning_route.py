import asyncio
import unittest
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestCleaningRoute(unittest.TestCase):
    @patch("addressforge.api.routes.cleaning.enqueue_cleaning")
    @patch("addressforge.core.common.db_cursor")
    def test_reclean_reviews_rolls_back_to_first_review_row_only(self, mock_db_cursor, mock_enqueue):
        from addressforge.api.routes.cleaning import CleaningRequest, reclean_reviews

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"min_id": 123}
        mock_cursor.rowcount = 7
        mock_db_cursor.return_value.__enter__.return_value = (mock_conn, mock_cursor)
        mock_enqueue.return_value = {"job_id": 99, "job_kind": "cleaning_once"}

        request = CleaningRequest(workspace_name="default", batch_size=500, requested_by="test", notes="")
        result = asyncio.run(reclean_reviews(request))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["affected_records"], 7)
        self.assertEqual(result["rolled_back_to"], 123)
        self.assertEqual(result["job"]["job_id"], 99)

        execute_calls = mock_cursor.execute.call_args_list
        self.assertIn('SELECT MIN(raw_id) as min_id FROM address_cleaning_result WHERE decision = "review"', execute_calls[0].args[0])
        self.assertIn('UPDATE address_cleaning_result SET decision = "pending"', execute_calls[1].args[0])
        self.assertIn('UPDATE control_setting SET setting_value = %s', execute_calls[2].args[0])
        self.assertEqual(execute_calls[2].args[1], ("122", "default"))

    @patch("addressforge.api.routes.cleaning.enqueue_cleaning")
    @patch("addressforge.core.common.db_cursor")
    def test_reclean_reviews_skips_cursor_rewind_when_no_review_rows(self, mock_db_cursor, mock_enqueue):
        from addressforge.api.routes.cleaning import CleaningRequest, reclean_reviews

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"min_id": None}
        mock_cursor.rowcount = 0
        mock_db_cursor.return_value.__enter__.return_value = (mock_conn, mock_cursor)
        mock_enqueue.return_value = {"job_id": 101, "job_kind": "cleaning_once"}

        request = CleaningRequest(workspace_name="default", batch_size=500, requested_by="test", notes="")
        result = asyncio.run(reclean_reviews(request))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["affected_records"], 0)
        self.assertIsNone(result["rolled_back_to"])
        execute_sql = [call.args[0] for call in mock_cursor.execute.call_args_list]
        self.assertEqual(sum('UPDATE control_setting SET setting_value = %s' in sql for sql in execute_sql), 0)


if __name__ == "__main__":
    unittest.main()
