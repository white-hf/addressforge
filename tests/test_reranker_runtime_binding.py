import unittest
import json
import os
from pathlib import Path
from unittest.mock import MagicMock
from addressforge.api.server import AddressPlatformService
from addressforge.services.reranker_service import RerankerService

class TestRerankerIsolation(unittest.TestCase):
    def test_version_isolation(self):
        # 1. Create two different manifests
        manifest_a = {
            "reranker_model_artifact": {
                "model_path": "runtime/models/reranker_a.cbm"
            }
        }
        manifest_b = {
            "reranker_model_artifact": {
                "model_path": "runtime/models/reranker_b.cbm"
            }
        }
        
        # 2. Build two different RerankerServices
        reranker_a = RerankerService(manifest=manifest_a)
        reranker_b = RerankerService(manifest=manifest_b)
        
        # 3. Build two different PlatformServices
        service_a = AddressPlatformService(reranker_service=reranker_a)
        service_b = AddressPlatformService(reranker_service=reranker_b)
        
        # 4. Assert isolation
        self.assertEqual(str(service_a._reranker_service.model_path), "runtime/models/reranker_a.cbm")
        self.assertEqual(str(service_b._reranker_service.model_path), "runtime/models/reranker_b.cbm")
        self.assertNotEqual(service_a._reranker_service, service_b._reranker_service)

    def test_runtime_identity_reporting(self):
        manifest = {
            "reranker_model_artifact": {
                "model_path": "runtime/models/custom_reranker.cbm"
            },
            "decision_model_artifact": {
                "model_path": "runtime/models/custom_decision.pkl",
                "metadata_path": "runtime/models/custom_decision.json"
            }
        }
        
        from addressforge.services.model_service import ModelService
        reranker = RerankerService(manifest=manifest)
        model_svc = ModelService(manifest=manifest)
        
        service = AddressPlatformService(
            model_service=model_svc,
            reranker_service=reranker
        )
        
        identity = service.describe_runtime()
        self.assertEqual(identity["reranker_model"]["model_path"], "runtime/models/custom_reranker.cbm")
        self.assertEqual(identity["decision_model"]["model_path"], "runtime/models/custom_decision.pkl")

    def test_governed_service_does_not_apply_mutable_local_policy_override(self):
        model_service = MagicMock()
        reranker_service = MagicMock()
        service = AddressPlatformService(
            decision_policy={"manifest_only_threshold": 0.91},
            model_service=model_service,
            reranker_service=reranker_service,
            allow_local_policy_override=False,
        )

        self.assertEqual(
            service._decision_policy,
            {"manifest_only_threshold": 0.91},
        )

if __name__ == "__main__":
    unittest.main()
