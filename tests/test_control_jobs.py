from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from addressforge.control.jobs import _run_reload_models_job


class TestControlJobs(unittest.TestCase):
    def test_run_reload_models_job_passes_active_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "artifact.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "decision_model_artifact": {
                            "model_path": "runtime/models/decision.pkl",
                            "metadata_path": "runtime/models/decision.json",
                        },
                        "reranker_model_artifact": {
                            "model_path": "runtime/models/reranker.cbm",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            snapshot = {
                "model": {
                    "artifact_path": str(artifact_path),
                    "model_version": "v_test",
                }
            }

            model_service_instance = MagicMock()
            reranker_service_instance = MagicMock()
            vector_engine_instance = MagicMock()

            with (
                patch("addressforge.models.bootstrap_default_registry", return_value=snapshot),
                patch("addressforge.services.model_service.get_model_service", return_value=model_service_instance) as mock_get_model_service,
                patch("addressforge.services.reranker_service.get_reranker_service", return_value=reranker_service_instance) as mock_get_reranker_service,
                patch("addressforge.core.retrieval.get_vector_engine", return_value=vector_engine_instance),
            ):
                result = _run_reload_models_job({"job_id": 123})

            self.assertEqual(result["status"], "success")
            mock_get_model_service.assert_called_once()
            mock_get_reranker_service.assert_called_once()
            model_service_instance.reload_models.assert_called_once()
            reranker_service_instance.reload_models.assert_called_once()
            self.assertTrue(model_service_instance.reload_models.call_args.kwargs["manifest"])
            self.assertTrue(reranker_service_instance.reload_models.call_args.kwargs["manifest"])
            self.assertIn("decision_model_artifact", model_service_instance.reload_models.call_args.kwargs["manifest"])


if __name__ == "__main__":
    unittest.main()
