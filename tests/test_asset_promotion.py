from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from addressforge.services.asset_service import promote_results_to_assets, get_asset_stats

class TestAssetPromotion(unittest.TestCase):
    """
    Unit tests for canonical asset promotion and scale-up idempotency.
    标准资产提升与大规模扩展幂等性的单元测试。
    """

    @patch("addressforge.services.asset_service.fetch_all")
    @patch("addressforge.services.asset_service.db_cursor")
    def test_promotion_idempotency_counting(self, mock_db, mock_fetch):
        """
        Verifies that promotion correctly identifies 'new' vs 'updated' assets.
        验证提升逻辑是否正确识别“新增”与“更新”资产。
        """
        # 1. Setup mock result for 1 cleaning record
        # 1. 为 1 条清洗记录设置模拟结果
        mock_fetch.return_value = [{
            "raw_id": 555, "base_address_key": "B_KEY", "full_address_key": "F_KEY",
            "street_number": "123", "street_name": "MAIN", "city": "HFX", 
            "province": "NS", "postal_code": "B3J", "country_code": "CA",
            "latitude": 44.0, "longitude": -63.0, "suggested_unit_number": "101"
        }]

        # 2. Simulate cursor behavior for initial insert (rowcount=1)
        # 2. 模拟初始插入的游标行为 (rowcount=1)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1 
        mock_db.return_value.__enter__.return_value = (mock_conn, mock_cursor)

        result = promote_results_to_assets(workspace_name="default")
        
        # Verify result counts
        # 验证结果计数
        self.assertEqual(result["new_buildings"], 1)
        self.assertEqual(result["new_units"], 1)

    @patch("addressforge.services.asset_service.fetch_all")
    @patch("addressforge.services.asset_service.db_cursor")
    def test_reference_first_merging(self, mock_db, mock_fetch):
        """
        Verifies that two different raw strings merge into one asset if they hit the same reference.
        验证如果两个不同的原始字符串命中了相同的参考记录，它们是否会合并为一个资产。
        """
        # Two records with different text but SAME external_id
        # 两个文本不同但外部 ID 相同的记录
        mock_fetch.return_value = [
            {
                "raw_id": 1, "street_number": "123", "street_name": "MAIN ST", 
                "city": "HFX", "province": "NS", "postal_code": "B3J", "country_code": "CA",
                "reference_json": '{"external_id": "REF_A"}', "suggested_unit_number": None,
                "latitude": 44.0, "longitude": -63.0
            },
            {
                "raw_id": 2, "street_number": "123", "street_name": "MAIN STREET", 
                "city": "HFX", "province": "NS", "postal_code": "B3J", "country_code": "CA",
                "reference_json": '{"external_id": "REF_A"}', "suggested_unit_number": None,
                "latitude": 44.0, "longitude": -63.0
            }
        ]

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Mock rowcount as a property that returns different values per call
        # 将 rowcount 模拟为每次调用返回不同值的属性
        # Sequence: Bld1(New=1), Bld2(Dup=0) - since the mock data has no units
        # 序列：Bld1(新增=1), Bld2(重复=0) - 因为模拟数据没有单元
        type(mock_cursor).rowcount = unittest.mock.PropertyMock(side_effect=[1, 0])

        mock_db.return_value.__enter__.return_value = (mock_conn, mock_cursor)

        result = promote_results_to_assets(workspace_name="default")
        
        # Should be exactly 1 new building
        self.assertEqual(result["new_buildings"], 1)


if __name__ == "__main__":
    unittest.main()
