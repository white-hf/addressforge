from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from addressforge.services.replay_service import _load_model_runtime


class TestReplayRuntime(unittest.TestCase):
    @patch("addressforge.services.replay_service.build_reranker_service_from_manifest")
    @patch("addressforge.services.replay_service.build_model_service_from_manifest")
    @patch("addressforge.services.replay_service.fetch_all")
    def test_load_model_runtime_prefers_metrics_runtime_binding_and_manifest(
        self,
        mock_fetch_all,
        mock_build_model_service,
        mock_build_reranker_service,
    ):
        mock_fetch_all.return_value = [
            {
                "workspace_name": "default",
                "model_version": "v_test",
                "default_profile": "base_canada",
                "artifact_path": None,
                "metrics_json": json.dumps(
                    {
                        "runtime_binding": {
                            "profile": "runtime_profile_v2",
                            "parsers": ["hybrid_canada", "libpostal"],
                            "decision_policy": {"high_confidence_accept_threshold": 0.91},
                        },
                        "decision_model_artifact": {
                            "metadata_path": "runtime/models/v_test.json",
                            "model_path": "runtime/models/v_test.pkl",
                            "legacy_model_path": "runtime/models/v_test.cbm",
                        },
                        "reranker_model_artifact": {
                            "model_path": "runtime/models/reranker_test.cbm",
                        },
                    }
                ),
            }
        ]
        sentinel_service = object()
        mock_build_model_service.return_value = sentinel_service
        
        sentinel_reranker = object()
        mock_build_reranker_service.return_value = sentinel_reranker

        runtime = _load_model_runtime("default", "v_test")

        self.assertTrue(runtime["ok"])
        self.assertEqual(runtime["profile"], "runtime_profile_v2")
        self.assertEqual(runtime["parsers"], ("hybrid_canada", "libpostal"))
        self.assertEqual(runtime["decision_policy"], {"high_confidence_accept_threshold": 0.91})
        self.assertIs(runtime["model_service"], sentinel_service)
        self.assertIs(runtime["reranker_service"], sentinel_reranker)
        
        mock_build_model_service.assert_called_once()
        mock_build_reranker_service.assert_called_once_with(
            {
                "decision_model_artifact": {
                    "metadata_path": "runtime/models/v_test.json",
                    "model_path": "runtime/models/v_test.pkl",
                    "legacy_model_path": "runtime/models/v_test.cbm",
                },
                "reranker_model_artifact": {
                    "model_path": "runtime/models/reranker_test.cbm",
                },
                "building_type_model_artifact": {}
            }
        )


if __name__ == "__main__":
    unittest.main()
