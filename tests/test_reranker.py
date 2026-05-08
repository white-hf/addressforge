from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from addressforge.learning.reranking_trainer import ParserRerankerTrainer
from addressforge.learning.trainer import _derive_candidate_feature_weights, _derive_candidate_pair_weights
from addressforge.api.server import _score_candidate

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
            parser_weights = weights.get("parser_weights", {})
            
            self.assertIn("hybrid_canada", parser_weights)
            self.assertIn("simple_rule", parser_weights)
            self.assertEqual(parser_weights["hybrid_canada"], 1.0)
            self.assertEqual(results.get("sample_size"), 3)

    def test_feature_extraction_integrity(self):
        """
        Tests if the feature collector properly handles empty datasets.
        测试特征收集器是否能正确处理空数据集。
        """
        with patch("addressforge.learning.reranking_trainer.fetch_all", return_value=[]):
            features = self.trainer.collect_training_features()
            self.assertEqual(len(features), 0)

    def test_runtime_loader_supports_nested_decision_policy_artifact(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from addressforge.api.server import RerankerArtifactLoader

        with TemporaryDirectory() as tmp_dir:
            artifact_path = Path(tmp_dir) / "artifact.json"
            artifact_path.write_text(
                '{"decision_policy": {"parser_weights": {"hybrid_canada": 0.7}, "match_rule_weights": {"__unit_present__": 0.8}}}',
                encoding="utf-8",
            )
            fake_model = {"artifact_path": str(artifact_path)}
            with patch("addressforge.api.server.get_active_model", return_value=fake_model):
                policy = RerankerArtifactLoader.load_decision_policy("default")
                self.assertEqual(policy["parser_weights"]["hybrid_canada"], 0.7)
                self.assertEqual(policy["match_rule_weights"]["__unit_present__"], 0.8)

    @patch("addressforge.learning.trainer._load_candidate_list_from_row")
    @patch("addressforge.learning.trainer.fetch_all")
    def test_candidate_feature_weights_are_derived_from_candidate_level_samples(self, mock_fetch, mock_candidates):
        mock_fetch.return_value = [
            {
                "label_json": '{"street_number":"1122","street_name":"Tower Road","unit_number":"312","building_type":"multi_unit"}',
                "parser_json": "{}",
                "raw_address_text": "1122 Tower Road, Unit 312 Halifax NS",
            },
            {
                "label_json": '{"street_number":"1119","street_name":"Tower Rd","unit_number":"706","building_type":"multi_unit"}',
                "parser_json": "{}",
                "raw_address_text": "1119 Tower Rd unit 706 Halifax NS",
            },
        ]
        mock_candidates.side_effect = [
            [
                {"parsed": {"street_number": "1122", "street_name": "Tower Road", "unit_number": None, "feature_vector": {"has_explicit_unit_hint": 1, "has_residential_unit_hint": 1}}},
                {"parsed": {"street_number": "1122", "street_name": "Tower Road", "unit_number": "312", "feature_vector": {"has_explicit_unit_hint": 1, "has_residential_unit_hint": 1}}},
            ],
            [
                {"parsed": {"street_number": "1119", "street_name": "Tower Rd", "unit_number": None, "feature_vector": {"has_explicit_unit_hint": 1, "has_residential_unit_hint": 1}}},
                {"parsed": {"street_number": "1119", "street_name": "Tower Rd", "unit_number": "706", "feature_vector": {"has_explicit_unit_hint": 1, "has_residential_unit_hint": 1}}},
            ],
        ]
        weights = _derive_candidate_feature_weights("test_ws")
        self.assertIn("__candidate_unit_with_hint__", weights)
        self.assertIn("__candidate_missing_unit_with_hint__", weights)
        self.assertIn("__candidate_unit_text_alignment__", weights)
        self.assertGreater(weights["__candidate_unit_with_hint__"], weights["__candidate_missing_unit_with_hint__"])

    def test_runtime_scoring_consumes_candidate_feature_weights(self):
        parsed = {
            "street_number": "1122",
            "street_name": "Tower Road",
            "unit_number": "312",
            "parse_confidence": 0.85,
            "unit_confidence": 0.8,
            "postal_confidence": 0.6,
            "feature_vector": {
                "has_explicit_unit_hint": 1,
                "has_residential_unit_hint": 1,
            },
        }
        baseline = _score_candidate(parsed)
        boosted = _score_candidate(
            parsed,
            candidate_feature_weights={
                "__candidate_has_unit__": 0.9,
                "__candidate_unit_with_hint__": 0.95,
                "__candidate_complete_street__": 0.8,
                "__candidate_unit_text_alignment__": 0.9,
            },
            raw_text="1122 Tower Road Unit 312 Halifax NS",
        )
        self.assertGreater(boosted, baseline)

    def test_runtime_scoring_penalizes_bare_number_unit_candidate(self):
        parsed = {
            "street_number": "194",
            "street_name": "Union St",
            "unit_number": "1676",
            "parse_confidence": 0.82,
            "unit_confidence": 0.75,
            "postal_confidence": 0.6,
            "feature_vector": {
                "has_explicit_unit_hint": 0,
                "has_residential_unit_hint": 0,
                "has_double_number_pattern": 1,
                "is_numbered_road_name": 0,
            },
        }
        baseline = _score_candidate(parsed, raw_text="194 Union St 1676 PICTOU NS")
        penalized = _score_candidate(
            parsed,
            raw_text="194 Union St 1676 PICTOU NS",
            candidate_feature_weights={
                "__candidate_bare_number_without_unit_hint__": 0.9,
            },
            candidate_pair_weights={
                "__penalize_bare_number_unit_candidate__": 0.95,
            },
        )
        self.assertLess(penalized, baseline)

    def test_runtime_scoring_preserves_bare_trailing_city_unit_candidate(self):
        parsed = {
            "street_number": "241",
            "street_name": "BROAD STREET",
            "unit_number": "105",
            "parse_confidence": 0.82,
            "unit_confidence": 0.75,
            "postal_confidence": 0.6,
            "feature_vector": {
                "has_explicit_unit_hint": 0,
                "has_residential_unit_hint": 0,
                "has_double_number_pattern": 1,
                "has_bare_trailing_unit_city_pattern": 1,
                "is_numbered_road_name": 0,
            },
        }
        baseline = _score_candidate(parsed, raw_text="241 Broad Street 105 Bedford NS")
        adjusted = _score_candidate(
            parsed,
            raw_text="241 Broad Street 105 Bedford NS",
            candidate_feature_weights={
                "__candidate_bare_number_without_unit_hint__": 0.9,
                "__candidate_bare_trailing_unit_city__": 0.95,
            },
            candidate_pair_weights={
                "__penalize_bare_number_unit_candidate__": 0.95,
                "__prefer_bare_trailing_unit_city_candidate__": 0.9,
            },
        )
        self.assertGreaterEqual(adjusted, baseline)

    def test_runtime_scoring_penalizes_placeholder_libpostal_candidate(self):
        placeholder = {
            "street_number": "123",
            "street_name": "MAIN ST",
            "unit_number": None,
            "city": None,
            "province": None,
            "postal_code": None,
            "parse_confidence": 0.9,
            "unit_confidence": 0.0,
            "postal_confidence": 0.0,
            "feature_vector": {"pattern": "libpostal"},
        }
        realistic = {
            "street_number": "11",
            "street_name": "EAGLE RD",
            "unit_number": None,
            "city": "Halifax",
            "province": "NS",
            "postal_code": "B0K 1X0",
            "parse_confidence": 0.3,
            "unit_confidence": 0.1,
            "postal_confidence": 0.5,
            "feature_vector": {"pattern": "simple_rule"},
        }
        placeholder_score = _score_candidate(
            placeholder,
            raw_text="N/A 11 EAGLE RD, FISHER'S GRANT, NS, B0K1X0, CA",
            parser_name="libpostal",
        )
        realistic_score = _score_candidate(
            realistic,
            raw_text="N/A 11 EAGLE RD, FISHER'S GRANT, NS, B0K1X0, CA",
            parser_name="simple_rule",
        )
        self.assertLess(placeholder_score, realistic_score)

    @patch("addressforge.learning.trainer._load_candidate_list_from_row")
    @patch("addressforge.learning.trainer.fetch_all")
    def test_candidate_pair_weights_capture_winner_vs_loser_signals(self, mock_fetch, mock_candidates):
        mock_fetch.return_value = [
            {
                "label_json": '{"street_number":"1122","street_name":"Tower Road","unit_number":"312","building_type":"multi_unit"}',
                "parser_json": "{}",
                "raw_address_text": "1122 Tower Road Unit 312 Halifax NS",
            },
            {
                "label_json": '{"street_number":"1119","street_name":"Tower Rd","unit_number":"706","building_type":"multi_unit"}',
                "parser_json": "{}",
                "raw_address_text": "1119 Tower Rd unit 706 Halifax NS",
            },
        ]
        mock_candidates.side_effect = [
            [
                {"parsed": {"street_number": "1122", "street_name": "Tower Road", "unit_number": None, "feature_vector": {"has_explicit_unit_hint": 1, "has_residential_unit_hint": 1}}},
                {"parsed": {"street_number": "1122", "street_name": "Tower Road", "unit_number": "312", "feature_vector": {"has_explicit_unit_hint": 1, "has_residential_unit_hint": 1}}},
            ],
            [
                {"parsed": {"street_number": "1119", "street_name": "Tower Rd", "unit_number": None, "feature_vector": {"has_explicit_unit_hint": 1, "has_residential_unit_hint": 1}}},
                {"parsed": {"street_number": "1119", "street_name": "Tower Rd", "unit_number": "706", "feature_vector": {"has_explicit_unit_hint": 1, "has_residential_unit_hint": 1}}},
            ],
        ]
        weights = _derive_candidate_pair_weights("test_ws")
        self.assertIn("__prefer_unit_candidate__", weights)
        self.assertIn("__prefer_text_aligned_unit__", weights)
        self.assertGreaterEqual(weights["__prefer_unit_candidate__"], 0.5)

    def test_runtime_scoring_consumes_candidate_pair_weights(self):
        parsed = {
            "street_number": "1119",
            "street_name": "Tower Rd",
            "unit_number": "706",
            "parse_confidence": 0.82,
            "unit_confidence": 0.75,
            "postal_confidence": 0.6,
            "feature_vector": {
                "has_explicit_unit_hint": 1,
                "has_residential_unit_hint": 1,
            },
        }
        baseline = _score_candidate(parsed, raw_text="1119 Tower Rd unit 706 Halifax NS")
        boosted = _score_candidate(
            parsed,
            raw_text="1119 Tower Rd unit 706 Halifax NS",
            candidate_pair_weights={
                "__prefer_unit_candidate__": 0.9,
                "__prefer_text_aligned_unit__": 0.95,
                "__prefer_residential_unit_candidate__": 0.85,
            },
        )
        self.assertGreater(boosted, baseline)

    def test_parse_candidates_recover_unit_before_validate(self):
        from addressforge.api.server import AddressPlatformService, AddressRequest

        service = AddressPlatformService()
        with patch("addressforge.api.server.RerankerArtifactLoader.load_decision_policy", return_value={}):
            parsed = service.parse(
                AddressRequest(
                    raw_address_text="1122 Tower Road, 312 Halifax NS",
                    city="Halifax",
                    province="NS",
                    country_code="CA",
                )
            )
        candidates = parsed.get("candidates") or []
        self.assertTrue(any(item.get("unit_number") == "312" for item in candidates))

if __name__ == "__main__":
    unittest.main()
