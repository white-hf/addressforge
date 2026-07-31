import unittest
import json
import tempfile
from unittest.mock import patch, MagicMock
from pathlib import Path
from addressforge.models.registry import promote_model
from addressforge.models.runtime_manifest import apply_runtime_manifest_contract


def _passing_release_comparison() -> dict:
    return {
        "active_available": True,
        "candidate_only": False,
        "promote_recommended": True,
        "regression_risk": 0.01,
        "gate_checks": [
            {
                "metric": "decision_f1",
                "candidate": 0.95,
                "active": 0.94,
                "delta": 0.01,
                "passed": True,
            }
        ],
    }


class TestRegistryReleaseGate(unittest.TestCase):
    @patch("addressforge.models.registry.db_cursor")
    @patch("addressforge.models.registry.fetch_all")
    def test_promote_model_blocks_on_invalid_readiness(self, mock_fetch_all, mock_db_cursor):
        # Setup mock model data
        metrics = {
            "release_benchmark": {"decision_f1": 0.95, "building_type_f1": 0.95, "unit_number_f1": 0.95, "unit_recall": 0.95, "commercial_f1": 0.95, "review_rate": 0.05, "reject_rate": 0.01},
            "release_comparison": _passing_release_comparison(),
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

    @patch("addressforge.models.runtime_manifest.Path.exists")
    @patch("addressforge.models.registry.db_cursor")
    @patch("addressforge.models.registry.fetch_all")
    def test_promote_model_blocks_on_missing_artifact_files(self, mock_fetch_all, mock_db_cursor, mock_path_exists):
        # Setup valid readiness but missing file
        metrics = {
            "release_benchmark": {"decision_f1": 0.95, "building_type_f1": 0.95, "unit_number_f1": 0.95, "unit_recall": 0.95, "commercial_f1": 0.95, "review_rate": 0.05, "reject_rate": 0.01},
            "release_comparison": _passing_release_comparison(),
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

    @patch("addressforge.models.runtime_manifest.Path.exists")
    @patch("addressforge.models.registry.db_cursor")
    @patch("addressforge.models.registry.fetch_all")
    def test_promote_model_blocks_on_missing_decision_metadata_sidecar(self, mock_fetch_all, mock_db_cursor, mock_path_exists):
        metrics = {
            "release_benchmark": {"decision_f1": 0.95, "building_type_f1": 0.95, "unit_number_f1": 0.95, "unit_recall": 0.95, "commercial_f1": 0.95, "review_rate": 0.05, "reject_rate": 0.01},
            "release_comparison": _passing_release_comparison(),
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

    @patch("addressforge.models.registry.db_cursor")
    @patch("addressforge.models.registry.fetch_all")
    def test_promote_model_blocks_when_required_runtime_component_is_absent(self, mock_fetch_all, mock_db_cursor):
        metrics = {
            "release_benchmark": {
                "decision_f1": 0.95,
                "building_type_f1": 0.95,
                "unit_number_f1": 0.95,
                "unit_recall": 0.95,
                "commercial_f1": 0.95,
                "review_rate": 0.05,
                "reject_rate": 0.01,
            },
            "release_comparison": _passing_release_comparison(),
            "replay_metrics": {"failures": 0, "processed_samples": 100},
            "decision_shadow_assist": {"shadow_advantage": 0.05, "disagreement_rate": 0.05},
            "decision_assist_rollout_readiness": {
                "status": "ready_for_assist_trial",
                "checks": {"shadow_beats_heuristic": True, "disagreement_rate_safe": True},
            },
            "manifest_schema_version": "1.0",
            "runtime_bundle_id": "default:canada_default:v_test",
            "artifact_hash_algorithm": "sha256",
            "workspace_name": "default",
            "model_name": "canada_default",
            "model_version": "v_test",
            "runtime_binding": {
                "profile": "base_canada",
                "parsers": ["hybrid_canada"],
                "decision_policy": {},
            },
        }
        mock_fetch_all.return_value = [
            {
                "model_id": 1,
                "workspace_name": "default",
                "model_name": "canada_default",
                "model_version": "v_test",
                "metrics_json": json.dumps(metrics),
                "artifact_path": None,
            }
        ]

        result = promote_model("default", 1)

        self.assertEqual(result["status"], "blocked")
        self.assertIn("Required runtime artifact component is missing", result["reason"])
        mock_db_cursor.assert_not_called()

    @patch("addressforge.models.registry.db_cursor")
    @patch("addressforge.models.registry.fetch_all")
    def test_promote_model_accepts_complete_hash_bound_runtime_manifest(self, mock_fetch_all, mock_db_cursor):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            decision_model = base / "decision.pkl"
            decision_metadata = base / "decision.json"
            reranker_model = base / "reranker.cbm"
            building_type_model = base / "building_type.cbm"
            decision_model.write_bytes(b"decision")
            decision_metadata.write_text("{}", encoding="utf-8")
            reranker_model.write_bytes(b"reranker")
            building_type_model.write_bytes(b"building")

            manifest = apply_runtime_manifest_contract(
                {
                    "workspace_name": "default",
                    "model_name": "canada_default",
                    "model_version": "v_test",
                    "runtime_binding": {
                        "profile": "base_canada",
                        "parsers": ["hybrid_canada"],
                        "decision_policy": {},
                    },
                    "decision_model_artifact": {
                        "model_type": "catboost",
                        "model_path": str(decision_model),
                        "metadata_path": str(decision_metadata),
                    },
                    "reranker_model_artifact": {
                        "model_type": "catboost",
                        "model_path": str(reranker_model),
                    },
                    "building_type_model_artifact": {
                        "model_type": "catboost_multiclass",
                        "model_path": str(building_type_model),
                    },
                }
            )
            metrics = {
                **manifest,
                "release_benchmark": {
                    "decision_f1": 0.95,
                    "building_type_f1": 0.95,
                    "unit_number_f1": 0.95,
                    "unit_recall": 0.95,
                    "commercial_f1": 0.95,
                    "review_rate": 0.05,
                    "reject_rate": 0.01,
                },
                "release_comparison": _passing_release_comparison(),
                "replay_metrics": {"failures": 0, "processed_samples": 100},
                "decision_shadow_assist": {
                    "shadow_advantage": 0.05,
                    "disagreement_rate": 0.05,
                },
                "decision_assist_rollout_readiness": {
                    "status": "ready_for_assist_trial",
                    "checks": {
                        "shadow_beats_heuristic": True,
                        "disagreement_rate_safe": True,
                    },
                },
            }
            mock_fetch_all.return_value = [
                {
                    "model_id": 1,
                    "workspace_name": "default",
                    "model_name": "canada_default",
                    "model_version": "v_test",
                    "default_profile": "base_canada",
                    "reference_version": "reference_current",
                    "metrics_json": json.dumps(metrics),
                    "artifact_path": None,
                }
            ]
            connection = MagicMock()
            cursor = MagicMock()
            cursor.fetchone.return_value = {"default_model_id": 9}
            mock_db_cursor.return_value.__enter__.return_value = (connection, cursor)

            result = promote_model("default", 1)

        self.assertEqual(result["status"], "promoted")
        self.assertEqual(result["model_id"], 1)
        self.assertEqual(result["previous_model_id"], 9)
        self.assertEqual(cursor.execute.call_count, 4)
        connection.commit.assert_called_once()

    @patch("addressforge.models.registry.db_cursor")
    @patch("addressforge.models.registry.fetch_all")
    @patch("addressforge.models.registry.build_release_readiness_report")
    def test_promote_model_dry_run_never_opens_write_transaction(
        self,
        mock_readiness,
        mock_fetch_all,
        mock_db_cursor,
    ):
        mock_fetch_all.return_value = [
            {
                "model_id": 51,
                "workspace_name": "default",
                "model_name": "canada_candidate",
                "model_version": "v_candidate",
            }
        ]
        mock_readiness.return_value = {
            "status": "ready",
            "ready": True,
            "reason": "All release gates passed.",
            "checks": [],
            "blockers": [],
            "final_f1": 0.95,
        }

        result = promote_model("default", 51, dry_run=True)

        self.assertEqual(result["status"], "ready")
        mock_db_cursor.assert_not_called()

    @patch("addressforge.models.registry.db_cursor")
    @patch("addressforge.models.registry.fetch_all")
    @patch("addressforge.models.registry.build_release_readiness_report")
    def test_promote_model_compare_and_swap_blocks_stale_activation(
        self,
        mock_readiness,
        mock_fetch_all,
        mock_db_cursor,
    ):
        mock_fetch_all.return_value = [
            {
                "model_id": 51,
                "workspace_name": "default",
                "model_name": "canada_candidate",
                "model_version": "v_candidate",
            }
        ]
        mock_readiness.return_value = {
            "status": "ready",
            "ready": True,
            "reason": "All release gates passed.",
            "checks": [],
            "blockers": [],
            "final_f1": 0.95,
        }
        connection = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = {"default_model_id": 43}
        mock_db_cursor.return_value.__enter__.return_value = (connection, cursor)

        result = promote_model(
            "default",
            51,
            expected_active_model_id=1,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("compare-and-swap failed", result["reason"])
        connection.rollback.assert_called_once_with()
        connection.commit.assert_not_called()
        self.assertEqual(cursor.execute.call_count, 1)

if __name__ == "__main__":
    unittest.main()
