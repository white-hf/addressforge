import unittest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from addressforge.console.server import app

class TestCleaningRoute(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("addressforge.core.common.fetch_all")
    @patch("addressforge.api.server.AddressPlatformService")
    def test_preview_top_review_opportunities(self, mock_service_class, mock_fetch_all):
        # Setup mock service
        mock_service = mock_service_class.return_value
        mock_service.validate.return_value = {"decision": "accept", "reason": "test"}

        # Mocking review opportunity items
        mock_fetch_all.side_effect = [
            # 1. _fetch_review_opportunity_items
            [
                {"source_name": "src1", "batch_id": "b1", "total_rows": 100, "review_count": 50, "accept_count": 20, "enrich_count": 20, "pending_count": 10, "review_rate": 0.5},
                {"source_name": "src2", "batch_id": "b2", "total_rows": 200, "review_count": 80, "accept_count": 50, "enrich_count": 50, "pending_count": 20, "review_rate": 0.4},
            ],
            # 2. _build_targeted_review_preview for Batch 1
            [
                {"raw_id": 1, "raw_address_text": "addr1", "source_name": "src1", "batch_id": "b1"},
            ],
            # 3. _build_targeted_review_preview for Batch 2
            [
                {"raw_id": 2, "raw_address_text": "addr2", "source_name": "src2", "batch_id": "b2"},
            ]
        ]

        response = self.client.post("/api/v1/cleaning/preview-top-review-opportunities", json={
            "opportunity_limit": 2,
            "preview_limit": 10
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("batch_summaries", data)
        self.assertEqual(len(data["batch_summaries"]), 2)
        
        # Check per-batch summary fields
        b1 = data["batch_summaries"][0]
        self.assertEqual(b1["source_name"], "src1")
        self.assertEqual(b1["batch_id"], "b1")
        self.assertIn("sampled_rows", b1)
        self.assertIn("decision_counts", b1)
        self.assertIn("projected_recovery_rate", b1)
        self.assertIn("leaderboard_total_rows", b1) # New field
        
        # Check aggregate fields in root
        self.assertIn("projected_recovery_rate", data)
        self.assertIn("decision_counts", data)
        # In my refactored code, sampled_rows is sum of per-batch sampled rows.
        # In the mock, Batch 1 gets 5 samples, Batch 2 gets 5 samples (10 / 2)
        self.assertEqual(data["sampled_rows"], 2) # Aggregate still matches because of my mock data

    @patch("addressforge.core.common.fetch_all")
    @patch("addressforge.core.common.db_cursor")
    @patch("addressforge.services.cleaning_service.enqueue_cleaning")
    @patch("addressforge.api.server.AddressPlatformService")
    def test_reclean_top_review_opportunities_returns_preview_summary(self, mock_service_class, mock_enqueue, mock_db_cursor, mock_fetch_all):
        mock_service = mock_service_class.return_value
        mock_service.validate.return_value = {"decision": "accept", "reason": "test"}
        mock_enqueue.return_value = {"job_id": 1}

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"min_id": 42}
        mock_cursor.rowcount = 7
        mock_db_cursor.return_value.__enter__.return_value = (mock_conn, mock_cursor)
        mock_db_cursor.return_value.__exit__.return_value = False

        mock_fetch_all.side_effect = [
            [
                {"source_name": "src1", "batch_id": "b1", "total_rows": 100, "review_count": 50, "accept_count": 20, "enrich_count": 20, "pending_count": 10, "review_rate": 0.5},
            ],
            [
                {"raw_id": 1, "raw_address_text": "addr1", "source_name": "src1", "batch_id": "b1"},
            ],
        ]

        response = self.client.post("/api/v1/cleaning/reclean-top-review-opportunities", json={
            "opportunity_limit": 1,
            "preview_limit": 10
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("preview_summary", data)
        self.assertIn("processed_batches", data)
        self.assertEqual(data["preview_summary"]["sampled_rows"], 1)
        self.assertEqual(data["preview_summary"]["batch_summaries"][0]["leaderboard_total_rows"], 100)
        self.assertEqual(data["affected_records"], 7)
        self.assertEqual(data["rolled_back_to"], 42)

if __name__ == "__main__":
    unittest.main()
