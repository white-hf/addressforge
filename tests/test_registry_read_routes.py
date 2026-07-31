from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from addressforge.api.server import AddressPlatformService, models, workspaces


class TestRegistryReadRoutes(unittest.IsolatedAsyncioTestCase):
    @patch("addressforge.api.server.list_models")
    async def test_models_route_is_read_only(self, mock_list_models) -> None:
        mock_list_models.return_value = [{"model_id": 1}]

        result = await models("workspace_a")

        self.assertEqual(result["workspace_name"], "workspace_a")
        self.assertEqual(result["models"], [{"model_id": 1}])
        mock_list_models.assert_called_once_with("workspace_a")

    @patch("addressforge.api.server.get_active_model")
    @patch("addressforge.api.server.get_workspace")
    @patch("addressforge.api.server.list_workspaces")
    async def test_workspaces_route_reads_registry_without_bootstrap(
        self,
        mock_list_workspaces,
        mock_get_workspace,
        mock_get_active_model,
    ) -> None:
        mock_list_workspaces.return_value = [{"workspace_name": "default"}]
        mock_get_workspace.return_value = {
            "workspace_name": "default",
            "default_model_id": 1,
        }
        mock_get_active_model.return_value = {"model_id": 1}

        result = await workspaces()

        self.assertEqual(result["active_model"]["model_id"], 1)
        mock_get_workspace.assert_called_once_with("default")
        mock_get_active_model.assert_called_once_with("default")

    @patch("addressforge.api.server.list_models")
    @patch("addressforge.api.server.get_active_model")
    @patch("addressforge.api.server.get_workspace")
    @patch("addressforge.core.common.fetch_all", return_value=[{"cnt": 0}])
    def test_model_info_reads_registry_without_bootstrap(
        self,
        _mock_fetch_all,
        mock_get_workspace,
        mock_get_active_model,
        mock_list_models,
    ) -> None:
        mock_get_workspace.return_value = {
            "workspace_name": "default",
            "default_model_id": 1,
        }
        mock_get_active_model.return_value = {
            "model_id": 1,
            "model_name": "canada_default",
            "model_version": "v1",
            "model_family": "baseline",
        }
        mock_list_models.return_value = [mock_get_active_model.return_value]
        service = AddressPlatformService(
            model_service=MagicMock(),
            reranker_service=MagicMock(),
            allow_local_policy_override=False,
        )

        result = service.model_info()

        self.assertEqual(result["active_model"]["model_id"], 1)
        mock_get_workspace.assert_called_once_with("default")
        mock_get_active_model.assert_called_once_with("default")


if __name__ == "__main__":
    unittest.main()
