from __future__ import annotations

import unittest
from addressforge.core.profiles.factory import get_profile, get_active_profile
from addressforge.core.profiles.canada import CanadaProfile
from addressforge.core.common import hybrid_canadian_parse_address

class TestProfileArchitecture(unittest.TestCase):
    """
    Tests for the Profile-driven architecture and cross-country abstractions.
    针对配置文件驱动架构与跨国家抽象的测试。
    """

    def test_factory_loading(self):
        """
        Verifies that the factory returns the correct profile instance.
        验证工厂是否返回正确的配置文件实例。
        """
        profile = get_profile("CA")
        self.assertIsInstance(profile, CanadaProfile)
        self.assertEqual(profile.country_code, "CA")

    def test_canada_metadata(self):
        """
        Verifies Canada-specific metadata like province tokens and GPS bounds.
        验证加拿大特定的元数据，如省份令牌和 GPS 边界。
        """
        profile = CanadaProfile()
        self.assertIn("NS", profile.province_tokens)
        self.assertIn("ON", profile.province_tokens)
        
        bounds = profile.gps_bounds
        self.assertEqual(bounds["lat_min"], 43.5)

    def test_feature_vector_generation(self):
        """
        Ensures that parsing an address generates a structured feature vector for ML.
        确保解析地址时会生成用于 ML 的结构化特征向量。
        """
        profile = get_profile("CA")
        address = "101-123 MAIN ST, HALIFAX, NS"
        result = hybrid_canadian_parse_address(address, profile=profile)
        
        self.assertIn("feature_vector", result)
        fv = result["feature_vector"]
        self.assertEqual(fv.get("country"), "CA")
        self.assertGreater(fv.get("text_len", 0), 0)

if __name__ == "__main__":
    unittest.main()
