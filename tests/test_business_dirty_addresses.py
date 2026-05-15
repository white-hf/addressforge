import unittest
from addressforge.services.business_service import _classify_dirty_categories, simple_string_similarity

class TestDirtyAddressLogic(unittest.TestCase):
    def test_history_mismatch(self):
        # Case: User has history unit 302, but current is missing unit
        categories = _classify_dirty_categories(
            decision="enrich",
            building_type="multi_unit",
            reason="Missing unit",
            hints={},
            suggested_unit_number=None,
            user_history_unit="302",
            asset_data={"has_known_units": True}
        )
        self.assertIn("history_mismatch", categories)

    def test_asset_gap(self):
        # Case: Matches building with units, but no user history
        categories = _classify_dirty_categories(
            decision="enrich",
            building_type="multi_unit",
            reason="Missing unit",
            hints={},
            suggested_unit_number=None,
            user_history_unit=None,
            asset_data={"has_known_units": True}
        )
        self.assertIn("asset_gap", categories)

    def test_hallucination_detection(self):
        # Case: "123 MAIN ST" is not in "3775 NS-359"
        raw_text = "3775 NS-359, Kings County"
        cand_sn = "123"
        cand_st = "MAIN ST"
        
        # Physical presence check
        is_hallucination = (cand_sn not in raw_text)
        self.assertTrue(is_hallucination)
        
        # Similarity check
        sim = simple_string_similarity(cand_st, raw_text)
        self.assertLess(sim, 0.3)

if __name__ == "__main__":
    unittest.main()
