from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from addressforge.learning.reranking_trainer import ParserRerankerTrainer

class TestParserReranker(unittest.TestCase):
    """
    Unit tests for the Parser Reranking and Decision Calibration logic.
    解析器重排与决策校准逻辑的单元测试。
    """

    def setUp(self):
        self.trainer = ParserRerankerTrainer(workspace_name="test_ws")

    @patch("addressforge.learning.reranking_trainer.ParserRerankerTrainer.collect_training_features")
    def test_weight_calculation_logic(self, mock_collect):
        """
        Verifies that weights are correctly calculated based on parser source performance.
        验证权重是否根据解析源的表现正确计算。
        """
        # Directly mock the feature list to avoid complex DB mock setup
        # 直接模拟特征列表，避免复杂的数据库模拟设置
        mock_collect.return_value = [
            {"unit_source": "hybrid_canada", "target_is_correct": 1},
            {"unit_source": "hybrid_canada", "target_is_correct": 1},
            {"unit_source": "simple_rule", "target_is_correct": 1}
        ]
        
        with patch("addressforge.learning.reranking_trainer.create_run", return_value=1), \
             patch("addressforge.learning.reranking_trainer.finish_run"), \
             patch("addressforge.learning.reranking_trainer.db_cursor"):
            
            results = self.trainer.train_reranking_weights()
            weights = results.get("weights", {})
            
            self.assertIn("hybrid_canada", weights)
            self.assertIn("simple_rule", weights)
            self.assertEqual(weights["hybrid_canada"], 1.0)
            self.assertEqual(results.get("sample_size"), 3)

    def test_feature_extraction_integrity(self):
        """
        Tests if the feature collector properly handles empty datasets.
        测试特征收集器是否能正确处理空数据集。
        """
        with patch("addressforge.learning.reranking_trainer.fetch_all", return_value=[]):
            features = self.trainer.collect_training_features()
            self.assertEqual(len(features), 0)

if __name__ == "__main__":
    unittest.main()
