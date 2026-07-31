from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from addressforge.models.registry import (
    _forward_only_lifecycle_status,
    get_active_model,
    register_model_version,
)


class TestRegistryActiveSource(unittest.TestCase):
    def tearDown(self) -> None:
        get_active_model.clear_cache()

    def test_lifecycle_registration_never_moves_backward(self) -> None:
        self.assertEqual(
            _forward_only_lifecycle_status("promoted", "evaluated"),
            "promoted",
        )
        self.assertEqual(
            _forward_only_lifecycle_status("deprecated", "trained"),
            "deprecated",
        )
        self.assertEqual(
            _forward_only_lifecycle_status("trained", "evaluated"),
            "evaluated",
        )

    @patch("addressforge.models.registry.get_workspace")
    @patch("addressforge.models.registry.fetch_all")
    def test_active_model_uses_workspace_pointer_even_when_flag_is_stale(
        self,
        mock_fetch_all,
        mock_get_workspace,
    ) -> None:
        mock_get_workspace.return_value = {
            "workspace_name": "default",
            "default_model_id": 1,
        }
        mock_fetch_all.return_value = [
            {
                "model_id": 1,
                "workspace_name": "default",
                "status": "evaluated",
                "is_default": 0,
            }
        ]

        active = get_active_model("default")

        self.assertEqual(active["model_id"], 1)
        self.assertEqual(active["_active_source"], "workspace_default_model_id")
        self.assertFalse(active["_registry_consistency"]["is_default_matches"])
        self.assertFalse(active["_registry_consistency"]["status_matches"])

    @patch("addressforge.models.registry.get_workspace")
    @patch("addressforge.models.registry.fetch_all")
    def test_active_model_allows_only_unique_legacy_default(
        self,
        mock_fetch_all,
        mock_get_workspace,
    ) -> None:
        mock_get_workspace.return_value = {
            "workspace_name": "legacy",
            "default_model_id": None,
        }
        mock_fetch_all.return_value = [
            {
                "model_id": 7,
                "workspace_name": "legacy",
                "status": "promoted",
                "is_default": 1,
            }
        ]

        active = get_active_model("legacy")

        self.assertEqual(active["model_id"], 7)
        self.assertEqual(active["_active_source"], "legacy_unique_is_default")
        self.assertFalse(active["_registry_consistency"]["workspace_pointer_matches"])

    @patch("addressforge.models.registry.get_workspace")
    @patch("addressforge.models.registry.fetch_all")
    def test_active_model_never_falls_back_to_latest_model(
        self,
        mock_fetch_all,
        mock_get_workspace,
    ) -> None:
        mock_get_workspace.return_value = {
            "workspace_name": "empty",
            "default_model_id": None,
        }
        mock_fetch_all.return_value = []

        self.assertIsNone(get_active_model("empty"))

    @patch("addressforge.models.registry.get_model")
    @patch("addressforge.models.registry.ensure_workspace")
    @patch("addressforge.models.registry.db_cursor")
    def test_evidence_registration_preserves_promoted_status_and_default_flag(
        self,
        mock_db_cursor,
        mock_ensure_workspace,
        mock_get_model,
    ) -> None:
        existing = {
            "model_id": 1,
            "workspace_name": "default",
            "model_name": "canada_default",
            "model_version": "v1",
            "status": "promoted",
            "is_default": 1,
        }
        mock_ensure_workspace.return_value = {
            "workspace_name": "default",
            "default_profile": "base_canada",
            "default_reference_version": "reference_current",
        }
        mock_get_model.side_effect = [existing, existing]
        connection = MagicMock()
        cursor = MagicMock()
        mock_db_cursor.return_value.__enter__.return_value = (connection, cursor)

        register_model_version(
            workspace_name="default",
            model_name="canada_default",
            model_version="v1",
            status="evaluated",
            evaluation_run_id=99,
            is_default=None,
        )

        sql = cursor.execute.call_args.args[0]
        params = cursor.execute.call_args.args[1]
        self.assertIn("status = %s", sql)
        self.assertNotIn("is_default = %s", sql)
        self.assertIn("promoted", params)
        connection.commit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
