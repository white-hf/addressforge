from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from addressforge.models.runtime_manifest import (
    RUNTIME_MANIFEST_SCHEMA_VERSION,
    apply_runtime_manifest_contract,
    resolve_runtime_manifest,
    validate_runtime_manifest,
)


class TestRuntimeManifest(unittest.TestCase):
    def _complete_manifest(self, base: Path) -> dict:
        decision_model = base / "decision.pkl"
        decision_metadata = base / "decision.json"
        reranker_model = base / "reranker.cbm"
        building_type_model = base / "building_type.cbm"
        decision_model.write_bytes(b"decision-v1")
        decision_metadata.write_text('{"features":["a","b"]}', encoding="utf-8")
        reranker_model.write_bytes(b"reranker-v1")
        building_type_model.write_bytes(b"building-type-v1")

        return apply_runtime_manifest_contract(
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

    def test_complete_hash_bound_manifest_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = self._complete_manifest(Path(tmpdir))
            validation = validate_runtime_manifest(
                manifest,
                model_row={
                    "model_id": 99,
                    "workspace_name": "default",
                    "model_name": "canada_default",
                    "model_version": "v_test",
                },
            )

        self.assertTrue(validation.ok, validation.to_dict())
        self.assertEqual(
            validation.identity["manifest_schema_version"],
            RUNTIME_MANIFEST_SCHEMA_VERSION,
        )
        self.assertEqual(
            validation.identity["runtime_bundle_id"],
            "default:canada_default:v_test",
        )

    def test_modified_artifact_fails_hash_validation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = self._complete_manifest(Path(tmpdir))
            Path(manifest["reranker_model_artifact"]["model_path"]).write_bytes(b"tampered")
            validation = validate_runtime_manifest(manifest)

        self.assertFalse(validation.ok)
        self.assertIn(
            "artifact_hash_mismatch",
            {issue.code for issue in validation.issues},
        )

    def test_missing_component_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = self._complete_manifest(Path(tmpdir))
            manifest.pop("building_type_model_artifact")
            validation = validate_runtime_manifest(manifest)

        self.assertFalse(validation.ok)
        self.assertIn(
            "artifact_component_missing",
            {issue.code for issue in validation.issues},
        )

    def test_registry_identity_mismatch_is_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = self._complete_manifest(Path(tmpdir))
            validation = validate_runtime_manifest(
                manifest,
                model_row={
                    "model_id": 99,
                    "workspace_name": "default",
                    "model_name": "canada_default",
                    "model_version": "different_version",
                },
            )

        self.assertFalse(validation.ok)
        self.assertIn(
            "manifest_identity_mismatch",
            {issue.code for issue in validation.issues},
        )

    def test_resolve_reads_nested_evaluation_metrics_without_losing_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            manifest = self._complete_manifest(base)
            evaluation_path = base / "evaluation.json"
            evaluation_path.write_text(
                json.dumps(
                    {
                        "workspace_name": "default",
                        "model_name": "canada_default",
                        "model_version": "v_test",
                        "metrics_json": manifest,
                    }
                ),
                encoding="utf-8",
            )
            model_row = {
                "model_id": 99,
                "workspace_name": "default",
                "model_name": "canada_default",
                "model_version": "v_test",
                "artifact_path": str(evaluation_path),
                "metrics_json": json.dumps({"metric_name": "decision_f1", "metric_value": 0.95}),
            }
            resolved = resolve_runtime_manifest(model_row)
            validation = validate_runtime_manifest(resolved, model_row=model_row)

        self.assertTrue(validation.ok, validation.to_dict())
        self.assertEqual(resolved["metric_name"], "decision_f1")
        self.assertIn("decision_model_artifact", resolved)


if __name__ == "__main__":
    unittest.main()
