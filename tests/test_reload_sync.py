import unittest
import json
import os
from pathlib import Path
from addressforge.api.server import AddressPlatformService
from addressforge.services.model_service import ModelService
from addressforge.services.reranker_service import RerankerService

class TestReloadSync(unittest.TestCase):
    def test_reload_synchronizes_binding(self):
        # 1. Setup a fake manifest with distinct settings
        custom_policy = {"custom_key": 99.9}
        manifest = {
            "runtime_binding": {
                "profile": "custom_profile",
                "parsers": ["simple_rule"],
                "decision_policy": custom_policy
            },
            "decision_model_artifact": {"model_path": "runtime/models/decision_catboost_v1.cbm"},
            "reranker_model_artifact": {"model_path": "runtime/models/reranker_catboost_v1.cbm"}
        }
        
        # Create artifact file for reload to find
        artifact_path = Path("runtime/models/test_reload_manifest.json")
        artifact_path.write_text(json.dumps(manifest))
        
        try:
            # 2. Mock bootstrap_default_registry to return our test manifest
            import addressforge.api.server as server
            original_bootstrap = server.bootstrap_default_registry
            server.bootstrap_default_registry = lambda: {
                "workspace": {"workspace_name": "default"},
                "model": {"artifact_path": str(artifact_path), "model_version": "test_v1"}
            }
            
            service = AddressPlatformService()
            
            # 3. Trigger reload
            service.reload_models()
            
            # 4. Verify sync
            runtime = service.describe_runtime()
            self.assertEqual(runtime["default_profile"], "custom_profile")
            self.assertIn("simple_rule", runtime["default_parsers"])
            self.assertEqual(len(runtime["default_parsers"]), 1)
            self.assertIn("custom_key", runtime["decision_policy_keys"])
            
            # Restore
            server.bootstrap_default_registry = original_bootstrap
            
        finally:
            if artifact_path.exists():
                artifact_path.unlink()

if __name__ == "__main__":
    unittest.main()
