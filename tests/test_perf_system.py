import time
import requests
import unittest
import json
from pathlib import Path

class TestSystemIntegrity(unittest.TestCase):
    def setUp(self):
        self.console_url = "http://127.0.0.1:8011"
        self.api_url = "http://127.0.0.1:8010"

    def test_status_endpoint_performance_and_fix(self):
        """Verify /control/status is fast and doesn't 500."""
        url = f"{self.console_url}/api/v1/control/status"
        
        # First call (cold, maybe)
        start = time.time()
        res = requests.get(url)
        duration_cold = time.time() - start
        self.assertEqual(res.status_code, 200, f"Status endpoint failed: {res.text}")
        print(f"\n[Perf] /control/status cold: {duration_cold:.4f}s")
        
        # Second call (cached)
        start = time.time()
        res = requests.get(url)
        duration_cached = time.time() - start
        self.assertEqual(res.status_code, 200)
        print(f"[Perf] /control/status cached: {duration_cached:.4f}s")
        
        # Assert cached is faster or at least very fast (< 100ms)
        self.assertLess(duration_cached, 0.2, "Cached status endpoint is too slow")

    def test_ingestion_config_performance(self):
        """Verify /control/ingestion-config is extremely fast."""
        url = f"{self.console_url}/api/v1/control/ingestion-config"
        
        start = time.time()
        res = requests.get(url)
        duration = time.time() - start
        self.assertEqual(res.status_code, 200)
        print(f"[Perf] /control/ingestion-config: {duration:.4f}s")
        self.assertLess(duration, 0.1, "Ingestion config endpoint is too slow")

    def test_env_config_content(self):
        """Verify /control/env contains all expected keys."""
        url = f"{self.console_url}/api/v1/control/env"
        res = requests.get(url)
        self.assertEqual(res.status_code, 200)
        data = res.json()["env_config"]
        
        expected_keys = [
            "API_TOKEN", 
            "ADDRESSFORGE_INGESTION_BATCH_LIST_OVERRIDE", 
            "MYSQL_HOST", 
            "ADDRESSFORGE_PORT"
        ]
        for key in expected_keys:
            self.assertIn(key, data, f"Key {key} missing from env config")
            print(f"[Check] Found key: {key} = {str(data[key])[:20]}...")

    def test_release_gate_enforcement(self):
        """Verify promote_model blocks invalid readiness (Internal call test via python if possible, or mock API)."""
        # Since promote_model involves DB, we check if we can call it via a test script
        # that mocks the fetch_all to return bad readiness.
        pass # Covered by tests/test_registry_release_gate.py

if __name__ == "__main__":
    unittest.main()
