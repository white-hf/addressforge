from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from addressforge.core.retrieval import VectorRetrievalEngine

class TestDualRetrievalGPS(unittest.TestCase):
    def test_gps_filtering_and_fallback(self):
        with TemporaryDirectory() as tmp_dir:
            engine = VectorRetrievalEngine(index_dir=tmp_dir)
            
            # Create mock reference records
            # Halifax coordinates: ~44.6488, -63.5752
            # Close building 1: ~44.6489, -63.5752 (~11m away)
            # Close building 2: ~44.6492, -63.5752 (~44m away)
            # Far building (conflict): ~44.7500, -63.5752 (~11km away)
            # Building with missing GPS coords
            records = [
                {
                    "reference_id": 1,
                    "street_number": "100",
                    "street_name": "Albro Lake Rd",
                    "city": "Halifax",
                    "province": "NS",
                    "reference_lat": 44.6489,
                    "reference_lon": -63.5752,
                },
                {
                    "reference_id": 2,
                    "street_number": "102",
                    "street_name": "Albro Lake Rd",
                    "city": "Halifax",
                    "province": "NS",
                    "reference_lat": 44.6492,
                    "reference_lon": -63.5752,
                },
                {
                    "reference_id": 3,
                    "street_number": "200",
                    "street_name": "Albro Lake Rd",
                    "city": "Halifax",
                    "province": "NS",
                    "reference_lat": 44.7500,
                    "reference_lon": -63.5752,
                },
                {
                    "reference_id": 4,
                    "street_number": "300",
                    "street_name": "Albro Lake Rd",
                    "city": "Halifax",
                    "province": "NS",
                    "reference_lat": None,
                    "reference_lon": None,
                }
            ]
            
            # Build index
            engine.build_index(records)
            
            # Reload engine to ensure clean init
            engine.reload_models()
            
            # Case 1: Query with GPS close to Building 1 and 2
            # Query text matches "Albro Lake Rd"
            # Halifax coordinates
            results = engine.retrieve("Albro Lake Rd", top_k=2, latitude=44.6488, longitude=-63.5752)
            
            # Building 1 and 2 should be returned because they are within 250m
            ref_ids = [r["reference_id"] for r in results]
            self.assertIn(1, ref_ids)
            self.assertIn(2, ref_ids)
            for r in results:
                self.assertFalse(r["gps_conflict"])
                self.assertIsNotNone(r["distance_meters"])
                self.assertLessEqual(r["distance_meters"], 250)
                
            # Case 2: Query with GPS close ONLY to building 3 (the far building)
            # Query: 44.7501, -63.5752
            results_far = engine.retrieve("Albro Lake Rd", top_k=1, latitude=44.7501, longitude=-63.5752)
            self.assertEqual(len(results_far), 1)
            self.assertEqual(results_far[0]["reference_id"], 3)
            self.assertFalse(results_far[0]["gps_conflict"])
            self.assertLessEqual(results_far[0]["distance_meters"], 250)
            
            # Case 3: Query with GPS far from ALL buildings
            # Query at ~45.0, -63.5752 (far from all buildings)
            results_conflict = engine.retrieve("Albro Lake Rd", top_k=2, latitude=45.0, longitude=-63.5752)
            
            # Should fallback to raw semantic top_k, but with gps_conflict=True and distance_meters set
            self.assertTrue(len(results_conflict) > 0)
            for r in results_conflict:
                if r["reference_id"] != 4:  # Candidate 4 has missing GPS, so no conflict info
                    self.assertTrue(r["gps_conflict"])
                    self.assertGreater(r["distance_meters"], 250)
                else:
                    self.assertFalse(r["gps_conflict"])
                    self.assertIsNone(r["distance_meters"])

            # Case 4: Missing query GPS parameters (backward compatibility check)
            results_no_gps = engine.retrieve("Albro Lake Rd", top_k=3)
            self.assertTrue(len(results_no_gps) > 0)
            for r in results_no_gps:
                self.assertIsNone(r["distance_meters"])
                self.assertFalse(r["gps_conflict"])

if __name__ == "__main__":
    unittest.main()
