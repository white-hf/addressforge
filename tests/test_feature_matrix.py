import unittest
import sys
import os
from pathlib import Path

# Add src to path
# 将 src 目录添加到路径中
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from addressforge.core.features import AddressFeatureExtractor

class TestFeatureMatrix(unittest.TestCase):
    def setUp(self):
        # Initialize with some known valid cities for testing
        self.extractor = AddressFeatureExtractor(valid_cities={"HALIFAX", "TRURO", "PICTOU", "DARTMOUTH"})

    def test_double_number_detection(self):
        raw = "194 union st 1676 PICTOU"
        parsed = {"street_number": "194", "street_name": "UNION ST", "city": "PICTOU", "province": "NS"}
        features = self.extractor.extract_features(raw, parsed)
        self.assertEqual(features["has_double_number"], 1, "Should detect multiple digit blocks")
        self.assertEqual(features["is_city_valid"], 1)

    def test_redundant_unit_detection(self):
        raw = "307 - 307 GRAND PRE"
        parsed = {"street_number": "307", "unit_number": "307", "street_name": "GRAND PRE"}
        features = self.extractor.extract_features(raw, parsed)
        self.assertEqual(features["is_unit_redundant"], 1, "Should detect identical SN and UN")

    def test_numbered_road_detection(self):
        # Case 1: Hwy followed by number (Classic numbered road)
        raw1 = "Hwy 102 Halifax NS"
        parsed1 = {"street_name": "HWY 102"}
        features1 = self.extractor.extract_features(raw1, parsed1)
        self.assertEqual(features1["is_numbered_road"], 1)

        # Case 2: Hwy as name part (Named highway)
        raw2 = "592 Bedford Hwy Halifax NS"
        parsed2 = {"street_name": "BEDFORD HWY"}
        features2 = self.extractor.extract_features(raw2, parsed2)
        self.assertEqual(features2["is_numbered_road"], 0)
        self.assertEqual(features2["has_hwy_keyword"], 1)

    def test_directional_detection(self):
        raw = "123 Main St North Halifax"
        parsed = {"street_name": "MAIN ST NORTH"}
        features = self.extractor.extract_features(raw, parsed)
        self.assertEqual(features["has_directional"], 1)

    def test_explicit_unit_hint(self):
        raw = "Apt 502 - 592 Bedford Hwy"
        parsed = {"unit_number": "502", "street_number": "592"}
        features = self.extractor.extract_features(raw, parsed)
        self.assertEqual(features["has_explicit_unit_hint"], 1, "Should detect 'Apt' keyword")

if __name__ == "__main__":
    unittest.main()
