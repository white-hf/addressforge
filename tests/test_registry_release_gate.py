import unittest
import json
from unittest.mock import patch, MagicMock
from pathlib import Path
from addressforge.models.registry import promote_model

class TestRegistryReleaseGate(unittest.TestCase):
    @patch("addressforge.models.registry.db_cursor")
    @patch("addressforge.models.registry.fetch_all")
    def test_promote_model_blocks_on_invalid_readiness(self, mock_fetch_all, mock_db_cursor):
        # Setup mock model data
        metrics = {
            "release_benchmark": {"decision_f1": 0.95, "building_type_f1": 0.95, "unit_number_f1": 0.95, "unit_recall": 0.95, "commercial_f1": 0.95, "review_rate": 0.05, "reject_rate": 0.01},
            "release_comparison": {"regression_risk": 0.01},
            "replay_metrics": {"failures": 0, "processed_samples": 100, "regression_detected": 0.01},
            "decision_shadow_assist": {"shadow_advantage": 0.05, "disagreement_rate": 0.05},
            # CASE A: Status is NOT ready_for_assist_trial
            "decision_assist_rollout_readiness": {
                "status": "needs_more_assist_calibration",
                "checks": {"shadow_beats_heuristic": True, "disagreement_rate_safe": True}
            }
        }
        
        mock_fetch_all.return_value = [{
            "model_id": 1,
            "workspace_name": "default",
            "model_version": "v_test",
            "metrics_json": json.dumps(metrics),
            "artifact_path": None
        }]
        
        # Test Case A
        result = promote_model("default", 1)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("ready_for_assist_trial", result["reason"])

        # CASE B: One sub-check is False
        metrics["decision_assist_rollout_readiness"] = {
            "status": "ready_for_assist_trial",
            "checks": {"shadow_beats_heuristic": False, "disagreement_rate_safe": True}
        }
        mock_fetch_all.return_value[0]["metrics_json"] = json.dumps(metrics)
        
        result = promote_model("default", 1)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Sub-checks failed", result["reason"])

    @patch("addressforge.models.registry.Path.exists")
    @patch("addressforge.models.registry.db_cursor")
    @patch("addressforge.models.registry.fetch_all")
    def test_promote_model_blocks_on_missing_artifact_files(self, mock_fetch_all, mock_db_cursor, mock_path_exists):
        # Setup valid readiness but missing file
        metrics = {
            "release_benchmark": {"decision_f1": 0.95, "building_type_f1": 0.95, "unit_number_f1": 0.95, "unit_recall": 0.95, "commercial_f1": 0.95, "review_rate": 0.05, "reject_rate": 0.01},
            "release_comparison": {"regression_risk": 0.01},
            "replay_metrics": {"failures": 0, "processed_samples": 100, "regression_detected": 0.01},
            "decision_shadow_assist": {"shadow_advantage": 0.05, "disagreement_rate": 0.05},
            "decision_assist_rollout_readiness": {
                "status": "ready_for_assist_trial",
                "checks": {"shadow_beats_heuristic": True, "disagreement_rate_safe": True}
            },
            "decision_model_artifact": {"model_path": "/tmp/missing-model.pkl"}
        }
        
        mock_fetch_all.return_value = [{
            "model_id": 1,
            "workspace_name": "default",
            "model_version": "v_test",
            "metrics_json": json.dumps(metrics),
            "artifact_path": None
        }]
        
        # Mock file missing
        mock_path_exists.return_value = False
        
        result = promote_model("default", 1)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Consistency Gate Failed", result["reason"])

    @patch("addressforge.models.registry.Path.exists")
    @patch("addressforge.models.registry.db_cursor")
    @patch("addressforge.models.registry.fetch_all")
    def test_promote_model_blocks_on_missing_decision_metadata_sidecar(self, mock_fetch_all, mock_db_cursor, mock_path_exists):
        metrics = {
            "release_benchmark": {"decision_f1": 0.95, "building_type_f1": 0.95, "unit_number_f1": 0.95, "unit_recall": 0.95, "commercial_f1": 0.95, "review_rate": 0.05, "reject_rate": 0.01},
            "release_comparison": {"regression_risk": 0.01},
            "replay_metrics": {"failures": 0, "processed_samples": 100, "regression_detected": 0.01},
            "decision_shadow_assist": {"shadow_advantage": 0.05, "disagreement_rate": 0.05},
            "decision_assist_rollout_readiness": {
                "status": "ready_for_assist_trial",
                "checks": {"shadow_beats_heuristic": True, "disagreement_rate_safe": True}
            },
            "decision_model_artifact": {
                "model_path": "/tmp/decision-model.pkl",
                "metadata_path": "/tmp/decision-model.json",
            }
        }

        mock_fetch_all.return_value = [{
            "model_id": 1,
            "workspace_name": "default",
            "model_version": "v_test",
            "metrics_json": json.dumps(metrics),
            "artifact_path": None
        }]

        mock_path_exists.side_effect = [True, False]

        result = promote_model("default", 1)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Consistency Gate Failed", result["reason"])

if __name__ == "__main__":
    unittest.main()
