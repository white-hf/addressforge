import unittest
import requests
import json
import time

class TestBuildingTypeOverride(unittest.TestCase):
    def setUp(self):
        self.api_url = "http://127.0.0.1:8010/api/v1/validate"

    def test_high_confidence_override(self):
        # We need a sample that is likely to be overridden if the model is trained.
        # For this test, we just check if ml_building_type is present in the response
        # and if the logic doesn't crash.
        payload = {
            "raw_address_text": "123 Main St, Halifax, NS",
            "include_steps": True
        }
        try:
            res = requests.post(self.api_url, json=payload)
            self.assertEqual(res.status_code, 200)
            data = res.json()
            
            # Verify shadow_assist contains ml_building_type and reranker impact
            self.assertIn("shadow_assist", data)
            sa = data["shadow_assist"]
            self.assertIn("ml_building_type", sa)
            self.assertIn("reranker_impact_detected", sa)
            
            # Verify runtime_identity presence
            self.assertIn("runtime_identity", data)
            ri = data["runtime_identity"]
            self.assertIn("decision_model", ri)
            self.assertIn("reranker_model", ri)
            
            print(f"Heuristic Building Type: {data.get('building_type')}")
            print(f"ML Predicted Building Type: {sa.get('ml_building_type')}")
            print(f"Reranker Impact Detected: {sa.get('reranker_impact_detected')}")
            
        except requests.exceptions.ConnectionError:
            self.skipTest("API Server not running on 8010")

    def test_rollback_api(self):
        rollback_url = "http://127.0.0.1:8010/api/v1/models/rollback"
        payload = {
            "workspace_name": "default",
            "notes": "System test rollback"
        }
        try:
            res = requests.post(rollback_url, json=payload)
            # This might fail if there's no previous model, which is fine, 
            # we just want to see if the endpoint exists and behaves correctly.
            if res.status_code == 200:
                print("Rollback successful")
                data = res.json()
                self.assertEqual(data["status"], "ok")
            elif res.status_code == 400:
                print(f"Rollback blocked (expected if no history): {res.json().get('detail')}")
            else:
                self.fail(f"Rollback endpoint returned unexpected status {res.status_code}")
        except requests.exceptions.ConnectionError:
            self.skipTest("API Server not running on 8010")

if __name__ == "__main__":
    unittest.main()
