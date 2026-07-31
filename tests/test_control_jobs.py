import unittest
from unittest.mock import MagicMock, patch

from addressforge.control.jobs import _run_reload_models_job


class TestControlJobs(unittest.TestCase):
    def test_run_reload_models_job_validates_governed_bundle(self) -> None:
        active_model = {"model_id": 51, "model_version": "v_contract"}
        vector_engine_instance = MagicMock()
        runtime_identity = {
            "mode": "governed",
            "registry": {"model_id": 51},
            "contract": {"ok": True},
        }

        with (
            patch("addressforge.models.get_active_model", return_value=active_model) as mock_get_active,
            patch(
                "addressforge.services.runtime_bundle.build_runtime_bundle_from_model_row",
                return_value={"ok": True, "runtime_identity": runtime_identity},
            ) as mock_build_bundle,
            patch(
                "addressforge.core.retrieval.get_vector_engine",
                return_value=vector_engine_instance,
            ),
        ):
            result = _run_reload_models_job(
                {"job_id": 123, "workspace_name": "worker_workspace"}
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["runtime_identity"], runtime_identity)
        mock_get_active.assert_called_once_with("worker_workspace")
        mock_build_bundle.assert_called_once_with(active_model, mode="governed")
        vector_engine_instance.reload_models.assert_called_once_with()

    def test_run_reload_models_job_fails_closed_before_index_reload(self) -> None:
        active_model = {"model_id": 1, "model_version": "legacy"}
        vector_engine_instance = MagicMock()

        with (
            patch("addressforge.models.get_active_model", return_value=active_model),
            patch(
                "addressforge.services.runtime_bundle.build_runtime_bundle_from_model_row",
                return_value={
                    "ok": False,
                    "reason": "runtime_manifest_invalid",
                    "detail": "artifact hash missing",
                },
            ),
            patch(
                "addressforge.core.retrieval.get_vector_engine",
                return_value=vector_engine_instance,
            ),
        ):
            with self.assertRaisesRegex(ValueError, "runtime_manifest_invalid"):
                _run_reload_models_job({"job_id": 124})

        vector_engine_instance.reload_models.assert_not_called()


if __name__ == "__main__":
    unittest.main()
