import unittest
import os
from pathlib import Path
from addressforge.services.model_service import ModelService

class TestModelServiceIndependence(unittest.TestCase):
    def test_instances_are_not_shared(self):
        # Create two instances
        svc1 = ModelService()
        svc2 = ModelService()
        
        self.assertIsNot(svc1, svc2, "ModelService should not be a singleton")
        
    def test_manifest_override(self):
        # Create a dummy manifest
        dummy_path = "runtime/models/dummy.cbm"
        manifest = {
            "decision_model_artifact": {
                "model_path": dummy_path,
                "metadata_path": "runtime/models/dummy.json"
            },
            "building_type_model_artifact": {
                "model_path": "runtime/models/dummy_bt.cbm"
            }
        }
        
        svc = ModelService(manifest=manifest)
        self.assertEqual(str(svc.model_path), dummy_path)
        self.assertEqual(str(svc.bt_model_path), "runtime/models/dummy_bt.cbm")

if __name__ == "__main__":
    unittest.main()
