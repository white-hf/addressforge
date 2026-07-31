from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from addressforge.models.runtime_manifest import apply_runtime_manifest_contract
from addressforge.services.runtime_bundle import build_runtime_bundle_from_model_row


class TestRuntimeBundle(unittest.TestCase):
    def _model_row(self, base: Path) -> dict:
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
                    "parsers": ["simple_rule", "hybrid_canada"],
                    "decision_policy": {"assist_policy_mode": "shadow_only"},
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
        return {
            "model_id": 99,
            "workspace_name": "default",
            "model_name": "canada_default",
            "model_version": "v_test",
            "default_profile": "base_canada",
            "artifact_path": None,
            "metrics_json": manifest,
        }

    @staticmethod
    def _loaded_model_service() -> MagicMock:
        service = MagicMock()
        service.model = object()
        service.bt_model = object()
        service.bt_model_path = Path("building_type.cbm")
        service._legacy_mode = False
        service._artifact_source = "manifest"
        service.describe_runtime.return_value = {
            "model_path": "decision.pkl",
            "metadata_path": "decision.json",
            "artifact_source": "manifest",
            "legacy_mode": False,
        }
        return service

    @staticmethod
    def _loaded_reranker_service() -> MagicMock:
        service = MagicMock()
        service.model = object()
        service._artifact_source = "manifest"
        service.describe_runtime.return_value = {
            "model_path": "reranker.cbm",
            "artifact_source": "manifest",
        }
        return service

    @patch("addressforge.services.runtime_bundle.build_reranker_service_from_manifest")
    @patch("addressforge.services.runtime_bundle.build_model_service_from_manifest")
    def test_governed_bundle_loads_only_after_contract_passes(
        self,
        mock_build_model_service,
        mock_build_reranker_service,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_row = self._model_row(Path(tmpdir))
            mock_build_model_service.return_value = self._loaded_model_service()
            mock_build_reranker_service.return_value = self._loaded_reranker_service()

            runtime = build_runtime_bundle_from_model_row(model_row, mode="governed")

        self.assertTrue(runtime["ok"], runtime)
        self.assertEqual(runtime["mode"], "governed")
        self.assertTrue(runtime["runtime_identity"]["contract"]["ok"])
        self.assertEqual(runtime["runtime_identity"]["runtime_load_issues"], [])

    @patch("addressforge.services.runtime_bundle.build_reranker_service_from_manifest")
    @patch("addressforge.services.runtime_bundle.build_model_service_from_manifest")
    def test_governed_bundle_rejects_invalid_contract_before_service_load(
        self,
        mock_build_model_service,
        mock_build_reranker_service,
    ):
        runtime = build_runtime_bundle_from_model_row(
            {
                "model_id": 43,
                "workspace_name": "default",
                "model_name": "canada_default",
                "model_version": "v1",
                "metrics_json": {},
                "artifact_path": None,
            },
            mode="governed",
        )

        self.assertFalse(runtime["ok"])
        self.assertEqual(runtime["reason"], "runtime_manifest_invalid")
        mock_build_model_service.assert_not_called()
        mock_build_reranker_service.assert_not_called()

    @patch("addressforge.services.runtime_bundle.build_reranker_service_from_manifest")
    @patch("addressforge.services.runtime_bundle.build_model_service_from_manifest")
    def test_governed_bundle_rejects_runtime_load_failure(
        self,
        mock_build_model_service,
        mock_build_reranker_service,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_row = self._model_row(Path(tmpdir))
            failed_model_service = self._loaded_model_service()
            failed_model_service.model = None
            mock_build_model_service.return_value = failed_model_service
            mock_build_reranker_service.return_value = self._loaded_reranker_service()

            runtime = build_runtime_bundle_from_model_row(model_row, mode="governed")

        self.assertFalse(runtime["ok"])
        self.assertEqual(runtime["reason"], "runtime_artifact_load_failed")
        self.assertIn(
            "decision_model_load_failed",
            {
                issue["code"]
                for issue in runtime["runtime_identity"]["runtime_load_issues"]
            },
        )

    @patch("addressforge.services.runtime_bundle.build_reranker_service_from_manifest")
    @patch("addressforge.services.runtime_bundle.build_model_service_from_manifest")
    def test_compatibility_mode_records_invalid_contract_and_fallbacks(
        self,
        mock_build_model_service,
        mock_build_reranker_service,
    ):
        fallback_model = MagicMock()
        fallback_model.model = None
        fallback_model.bt_model = None
        fallback_model.bt_model_path = Path("legacy-building.cbm")
        fallback_model._legacy_mode = True
        fallback_model._artifact_source = "legacy_path"
        fallback_model.describe_runtime.return_value = {
            "artifact_source": "legacy_path",
            "legacy_mode": True,
        }
        fallback_reranker = MagicMock()
        fallback_reranker.model = None
        fallback_reranker._artifact_source = "legacy_path"
        fallback_reranker.describe_runtime.return_value = {
            "artifact_source": "legacy_path",
        }
        mock_build_model_service.return_value = fallback_model
        mock_build_reranker_service.return_value = fallback_reranker

        runtime = build_runtime_bundle_from_model_row(
            {
                "model_id": 1,
                "workspace_name": "default",
                "model_name": "canada_default",
                "model_version": "legacy",
                "metrics_json": {},
                "artifact_path": None,
            },
            mode="compatibility",
        )

        self.assertTrue(runtime["ok"])
        self.assertFalse(runtime["runtime_identity"]["contract"]["ok"])
        self.assertTrue(runtime["runtime_identity"]["runtime_load_issues"])

    @patch("addressforge.services.runtime_bundle.build_reranker_service_from_manifest")
    @patch("addressforge.services.runtime_bundle.build_model_service_from_manifest")
    def test_two_bundle_loads_receive_distinct_service_instances(
        self,
        mock_build_model_service,
        mock_build_reranker_service,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_row = self._model_row(Path(tmpdir))
            model_a = self._loaded_model_service()
            model_b = self._loaded_model_service()
            reranker_a = self._loaded_reranker_service()
            reranker_b = self._loaded_reranker_service()
            mock_build_model_service.side_effect = [model_a, model_b]
            mock_build_reranker_service.side_effect = [reranker_a, reranker_b]

            runtime_a = build_runtime_bundle_from_model_row(model_row, mode="governed")
            runtime_b = build_runtime_bundle_from_model_row(model_row, mode="governed")

        self.assertIsNot(runtime_a["model_service"], runtime_b["model_service"])
        self.assertIsNot(runtime_a["reranker_service"], runtime_b["reranker_service"])


if __name__ == "__main__":
    unittest.main()
