from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from addressforge.learning.gold import seed_active_learning_queue

class TestGoldSampling(unittest.TestCase):
    """
    Unit tests for the stratified sampling and gold expansion logic.
    针对分层采样与金标扩样逻辑的单元测试。
    """

    @patch("addressforge.learning.gold.fetch_all")
    @patch("addressforge.learning.gold.db_cursor")
    @patch("addressforge.learning.gold.create_run", return_value=99)
    @patch("addressforge.learning.gold.finish_run")
    def test_stratified_sampling_distribution(self, mock_finish, mock_create, mock_db, mock_fetch):
        """
        Verifies that sampling is requested for each building type strata.
        验证是否针对每个建筑类型层级都请求了采样。
        """
        # Mock fetch_all to return data for each strata call
        # 模拟 fetch_all，为每个层级调用返回数据
        mock_fetch.side_effect = [
            [{"raw_id": 101, "confidence": 0.3}], # commercial
            [{"raw_id": 201, "confidence": 0.4}, {"raw_id": 202, "confidence": 0.5}], # multi_unit
            [{"raw_id": 301, "confidence": 0.5}] # single_unit
        ]

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.return_value.__enter__.return_value = (mock_conn, mock_cursor)

        # Request a limit of 10 samples
        # 请求 10 个样本的限制
        result = seed_active_learning_queue(workspace_name="default", limit=10)
        
        # Total inserted should be 1 + 2 + 1 = 4
        # 总插入数应为 1 + 2 + 1 = 4
        self.assertEqual(result["inserted"], 4)
        
        # Verify fetch_all was called 3 times (one per strata)
        # 验证 fetch_all 被调用了 3 次 (每个层级一次)
        self.assertEqual(mock_fetch.call_count, 3)

if __name__ == "__main__":
    unittest.main()
