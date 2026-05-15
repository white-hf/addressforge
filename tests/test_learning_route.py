import unittest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from addressforge.console.server import app

class TestLearningRoute(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("addressforge.learning.gold.seed_active_learning_from_residual_buckets")
    def test_reseed_residual_buckets(self, mock_seed_fn):
        # Setup mock return
        mock_seed_fn.return_value = {
            "run_id": 123,
            "inserted": 10,
            "workspace_name": "default"
        }

        response = self.client.post("/api/v1/cleaning/reseed-residual-buckets", json={
            "preview_limit": 50,
            "source_name": "test_source",
            "batch_id": "test_batch"
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["inserted"], 10)
        self.assertEqual(data["run_id"], 123)
        
        # Verify function call includes scoping parameters
        mock_seed_fn.assert_called_once_with(
            workspace_name="default",
            limit=50,
            target_buckets=None,
            source_name="test_source",
            batch_id="test_batch"
        )

    def test_reseed_residual_buckets_blocks_empty_scope(self):
        # Test Case: Empty scope (no source_name or batch_id)
        response = self.client.post("/api/v1/cleaning/reseed-residual-buckets", json={
            "preview_limit": 50
        })

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("Scoping required", data["detail"])

if __name__ == "__main__":
    unittest.main()
