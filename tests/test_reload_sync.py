import unittest
from unittest.mock import MagicMock, patch

from addressforge.api.server import AddressPlatformService


class TestReloadSync(unittest.TestCase):
    @patch("addressforge.api.server.build_runtime_bundle_from_model_row")
    @patch("addressforge.api.server.get_active_model")
    def test_startup_uses_governed_bundle_without_compatibility_reload(
        self,
        mock_get_active_model,
        mock_build_bundle,
    ):
        active_model = {
            "model_id": 51,
            "model_version": "v_contract",
            "artifact_path": "must-not-be-read.json",
        }
        model_service = MagicMock()
        reranker_service = MagicMock()
        mock_get_active_model.return_value = active_model
        mock_build_bundle.return_value = {
            "ok": True,
            "profile": "governed_profile",
            "parsers": ("simple_rule",),
            "decision_policy": {"policy_source": "manifest"},
            "model_service": model_service,
            "reranker_service": reranker_service,
            "runtime_identity": {"mode": "governed", "contract": {"ok": True}},
        }

        service = AddressPlatformService(
            workspace_name="isolated_workspace",
            allow_local_policy_override=False,
        )

        runtime = service.describe_runtime()
        self.assertEqual(runtime["workspace_name"], "isolated_workspace")
        self.assertEqual(runtime["default_profile"], "governed_profile")
        self.assertEqual(runtime["runtime_bundle"]["mode"], "governed")
        self.assertIs(service._model_service, model_service)
        self.assertIs(service._reranker_service, reranker_service)
        mock_get_active_model.assert_called_once_with("isolated_workspace")
        mock_build_bundle.assert_called_once_with(active_model, mode="governed")

    @patch("addressforge.api.server.get_workspace.clear_cache")
    @patch("addressforge.api.server.get_active_model.clear_cache")
    @patch("addressforge.api.server.build_runtime_bundle_from_model_row")
    @patch("addressforge.api.server.get_active_model")
    def test_reload_synchronizes_governed_bundle(
        self,
        mock_get_active_model,
        mock_build_bundle,
        mock_clear_active_cache,
        mock_clear_workspace_cache,
    ):
        active_model = {"model_id": 51, "model_version": "v_contract"}
        model_service = MagicMock()
        reranker_service = MagicMock()
        mock_get_active_model.return_value = active_model
        mock_build_bundle.return_value = {
            "ok": True,
            "profile": "custom_profile",
            "parsers": ("simple_rule",),
            "decision_policy": {"custom_key": 99.9},
            "model_service": model_service,
            "reranker_service": reranker_service,
            "runtime_identity": {"mode": "governed", "contract": {"ok": True}},
        }
        service = AddressPlatformService(
            model_service=MagicMock(),
            reranker_service=MagicMock(),
            workspace_name="reload_workspace",
            allow_local_policy_override=False,
        )
        service._vector_engine = MagicMock()

        service.reload_models()

        runtime = service.describe_runtime()
        self.assertEqual(runtime["default_profile"], "custom_profile")
        self.assertEqual(runtime["default_parsers"], ["simple_rule"])
        self.assertIn("custom_key", runtime["decision_policy_keys"])
        self.assertEqual(runtime["runtime_bundle"]["mode"], "governed")
        self.assertIs(service._model_service, model_service)
        self.assertIs(service._reranker_service, reranker_service)
        mock_build_bundle.assert_called_once_with(active_model, mode="governed")
        mock_get_active_model.assert_called_once_with("reload_workspace")
        mock_clear_active_cache.assert_called_once()
        mock_clear_workspace_cache.assert_called_once()

    @patch("addressforge.api.server.get_workspace.clear_cache")
    @patch("addressforge.api.server.get_active_model.clear_cache")
    @patch("addressforge.api.server.build_runtime_bundle_from_model_row")
    @patch("addressforge.api.server.get_active_model")
    def test_reload_preserves_current_services_when_contract_is_invalid(
        self,
        mock_get_active_model,
        mock_build_bundle,
        _mock_clear_active_cache,
        _mock_clear_workspace_cache,
    ):
        mock_get_active_model.return_value = {"model_id": 1, "model_version": "legacy"}
        mock_build_bundle.return_value = {
            "ok": False,
            "reason": "runtime_manifest_invalid",
            "detail": "hash missing",
        }
        current_model_service = MagicMock()
        current_reranker_service = MagicMock()
        service = AddressPlatformService(
            model_service=current_model_service,
            reranker_service=current_reranker_service,
            allow_local_policy_override=False,
        )

        with self.assertRaisesRegex(RuntimeError, "runtime_manifest_invalid"):
            service.reload_models()

        self.assertIs(service._model_service, current_model_service)
        self.assertIs(service._reranker_service, current_reranker_service)


if __name__ == "__main__":
    unittest.main()
