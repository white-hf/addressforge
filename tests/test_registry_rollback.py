from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from addressforge.models.registry import rollback_model


class TestRegistryRollback(unittest.TestCase):
    @patch("addressforge.models.registry.validate_runtime_manifest")
    @patch("addressforge.models.registry.resolve_runtime_manifest")
    @patch("addressforge.models.registry.fetch_all")
    @patch("addressforge.models.registry.get_active_model")
    @patch("addressforge.models.registry.db_cursor")
    def test_rollback_is_one_transaction_with_explicit_target(
        self,
        mock_db_cursor,
        mock_get_active_model,
        mock_fetch_all,
        mock_resolve_manifest,
        mock_validate_manifest,
    ) -> None:
        mock_get_active_model.return_value = {"model_id": 51}
        target = {
            "model_id": 43,
            "workspace_name": "default",
            "model_name": "canada_default",
            "model_version": "v_previous",
            "status": "deprecated",
            "default_profile": "base_canada",
            "reference_version": "reference_current",
        }
        mock_fetch_all.return_value = [target]
        mock_resolve_manifest.return_value = {"model_version": "v_previous"}
        validation = MagicMock(ok=True)
        validation.to_dict.return_value = {"ok": True}
        mock_validate_manifest.return_value = validation
        connection = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = {"default_model_id": 51}
        mock_db_cursor.return_value.__enter__.return_value = (connection, cursor)

        result = rollback_model(
            "default",
            target_model_id=43,
            expected_active_model_id=51,
        )

        self.assertEqual(result["status"], "rolled_back")
        self.assertEqual(result["model_id"], 43)
        self.assertEqual(result["previous_model_id"], 51)
        self.assertEqual(cursor.execute.call_count, 4)
        connection.commit.assert_called_once_with()
        connection.rollback.assert_not_called()

    @patch("addressforge.models.registry.validate_runtime_manifest")
    @patch("addressforge.models.registry.resolve_runtime_manifest")
    @patch("addressforge.models.registry.fetch_all")
    @patch("addressforge.models.registry.get_active_model")
    @patch("addressforge.models.registry.db_cursor")
    def test_rollback_dry_run_does_not_write(
        self,
        mock_db_cursor,
        mock_get_active_model,
        mock_fetch_all,
        mock_resolve_manifest,
        mock_validate_manifest,
    ) -> None:
        mock_get_active_model.return_value = {"model_id": 51}
        mock_fetch_all.return_value = [
            {
                "model_id": 43,
                "workspace_name": "default",
                "model_version": "v_previous",
                "status": "deprecated",
            }
        ]
        mock_resolve_manifest.return_value = {}
        validation = MagicMock(ok=True)
        validation.to_dict.return_value = {"ok": True}
        mock_validate_manifest.return_value = validation

        result = rollback_model("default", target_model_id=43, dry_run=True)

        self.assertEqual(result["status"], "ready")
        mock_db_cursor.assert_not_called()

    @patch("addressforge.models.registry.validate_runtime_manifest")
    @patch("addressforge.models.registry.resolve_runtime_manifest")
    @patch("addressforge.models.registry.fetch_all")
    @patch("addressforge.models.registry.get_active_model")
    @patch("addressforge.models.registry.db_cursor")
    def test_rollback_blocks_stale_active_without_partial_demotion(
        self,
        mock_db_cursor,
        mock_get_active_model,
        mock_fetch_all,
        mock_resolve_manifest,
        mock_validate_manifest,
    ) -> None:
        mock_get_active_model.return_value = {"model_id": 51}
        mock_fetch_all.return_value = [
            {
                "model_id": 43,
                "workspace_name": "default",
                "model_version": "v_previous",
                "status": "deprecated",
            }
        ]
        mock_resolve_manifest.return_value = {}
        validation = MagicMock(ok=True)
        validation.to_dict.return_value = {"ok": True}
        mock_validate_manifest.return_value = validation
        connection = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = {"default_model_id": 52}
        mock_db_cursor.return_value.__enter__.return_value = (connection, cursor)

        result = rollback_model(
            "default",
            target_model_id=43,
            expected_active_model_id=51,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("compare-and-swap failed", result["reason"])
        self.assertEqual(cursor.execute.call_count, 1)
        connection.rollback.assert_called_once_with()
        connection.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
