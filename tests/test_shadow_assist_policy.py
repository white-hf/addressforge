from __future__ import annotations

import unittest
from unittest.mock import patch

from addressforge.api.server import AddressPlatformService, AddressRequest


class DummyModelService:
    def predict_decision(self, *args, **kwargs):  # pragma: no cover - not used in direct policy test
        return {"status": "no_model", "ml_score": 0.0}

    def predict_building_type(self, *args, **kwargs):  # pragma: no cover - not used in direct policy test
        return {"status": "no_model", "probabilities": {}}


class DummyRerankerService:
    def rerank_candidates(self, raw_text, candidates, semantic_anchors=None):
        return list(candidates)


class DummyVectorEngine:
    def retrieve(self, raw_text, top_k=3):
        return []


class DummyReferenceMatcher:
    def match(self, *args, **kwargs):
        return None

    def diagnose_gap(self, *args, **kwargs):
        return "reference_missing"


class TestShadowAssistPolicy(unittest.TestCase):
    def setUp(self):
        self.service = AddressPlatformService(
            model_service=DummyModelService(),
            reranker_service=DummyRerankerService(),
        )
        self.service._vector_engine = DummyVectorEngine()
        self.service._reference_matcher = DummyReferenceMatcher()

    def test_accept_recovery_requires_guards_to_pass(self):
        result = self.service._shadow_assist_recommendation(
            heuristic_decision="review",
            ml_result={"ml_decision": "accept", "ml_score": 0.81},
            reason="Parser confidence is moderate; review is safer.",
            parse_score=0.74,
            ref_score=0.72,
            building_type="single_unit",
            parser_disagreement=False,
            gps_conflict=False,
        )
        self.assertTrue(result["eligible"])
        self.assertEqual(result["recommended_decision"], "accept")
        self.assertEqual(result["guard_reason"], "eligible_accept_recovery")

    def test_accept_recovery_is_blocked_by_parser_disagreement(self):
        result = self.service._shadow_assist_recommendation(
            heuristic_decision="review",
            ml_result={"ml_decision": "accept", "ml_score": 0.92},
            reason="Strong parser candidates disagree on the structured address.",
            parse_score=0.81,
            ref_score=0.77,
            building_type="single_unit",
            parser_disagreement=True,
            gps_conflict=False,
        )
        self.assertFalse(result["eligible"])
        self.assertIsNone(result["recommended_decision"])
        self.assertEqual(result["guard_reason"], "parser_disagreement_guard")

    def test_review_escalation_requires_trigger(self):
        result = self.service._shadow_assist_recommendation(
            heuristic_decision="accept",
            ml_result={"ml_decision": "review", "ml_score": 0.66},
            reason="Parser confidence is high enough without reference confirmation.",
            parse_score=0.86,
            ref_score=0.84,
            building_type="single_unit",
            parser_disagreement=False,
            gps_conflict=False,
        )
        self.assertFalse(result["eligible"])
        self.assertEqual(result["guard_reason"], "no_guard_trigger_for_review")

    @patch.object(AddressPlatformService, "parse")
    def test_validate_accepts_complete_single_unit_at_moderate_confidence(self, mock_parse):
        mock_parse.return_value = {
            "candidates": [
                {
                    "street_number": "1456",
                    "street_name": "HERITAGE COURT",
                    "unit_number": None,
                    "city": "FALL RIVER",
                    "province": "NS",
                    "postal_code": None,
                    "score": 0.76,
                    "parser_name": "hybrid_canada",
                    "parsed": {
                        "street_number": "1456",
                        "street_name": "HERITAGE COURT",
                        "unit_number": None,
                        "city": "FALL RIVER",
                        "province": "NS",
                        "postal_code": None,
                        "feature_vector": {"pattern": "plain_house"},
                    },
                }
            ]
        }
        result = self.service.validate(AddressRequest(raw_address_text="1456 Heritage Court Fall River NS"))
        self.assertEqual(result["decision"], "accept")
        self.assertEqual(
            result["reason"],
            "Single-unit residential address is complete enough to accept at moderate confidence.",
        )

    @patch.object(AddressPlatformService, "parse")
    def test_validate_enriches_multi_unit_missing_unit_at_moderate_confidence(self, mock_parse):
        mock_parse.return_value = {
            "candidates": [
                {
                    "street_number": "200",
                    "street_name": "MAIN ST",
                    "unit_number": None,
                    "city": "HALIFAX",
                    "province": "NS",
                    "postal_code": None,
                    "score": 0.71,
                    "parser_name": "hybrid_canada",
                    "parsed": {
                        "street_number": "200",
                        "street_name": "MAIN ST",
                        "unit_number": None,
                        "city": "HALIFAX",
                        "province": "NS",
                        "postal_code": None,
                        "unit_source": "residential_hint",
                        "feature_vector": {"pattern": "plain_house"},
                    },
                }
            ]
        }
        with patch("addressforge.api.server.infer_structure_type", return_value="multi_unit"):
            result = self.service.validate(AddressRequest(raw_address_text="200 Main St Halifax NS"))
        self.assertEqual(result["decision"], "enrich")
        self.assertEqual(
            result["reason"],
            "Multi-unit residential address is likely valid, but unit details may be missing.",
        )

    @patch.object(AddressPlatformService, "parse")
    def test_validate_accepts_single_unit_on_soft_unit_only_disagreement(self, mock_parse):
        mock_parse.return_value = {
            "candidates": [
                {
                    "street_number": "1456",
                    "street_name": "HERITAGE COURT",
                    "unit_number": None,
                    "city": "FALL RIVER",
                    "province": "NS",
                    "postal_code": None,
                    "score": 0.77,
                    "parser_name": "hybrid_canada",
                    "parsed": {
                        "street_number": "1456",
                        "street_name": "HERITAGE COURT",
                        "unit_number": None,
                        "city": "FALL RIVER",
                        "province": "NS",
                        "postal_code": None,
                        "feature_vector": {"pattern": "plain_house"},
                    },
                },
                {
                    "street_number": "1456",
                    "street_name": "HERITAGE COURT",
                    "unit_number": "5",
                    "city": "FALL RIVER",
                    "province": "NS",
                    "postal_code": None,
                    "score": 0.74,
                    "parser_name": "libpostal",
                    "parsed": {
                        "street_number": "1456",
                        "street_name": "HERITAGE COURT",
                        "unit_number": "5",
                        "city": "FALL RIVER",
                        "province": "NS",
                        "postal_code": None,
                        "feature_vector": {"pattern": "plain_house"},
                    },
                },
            ]
        }
        result = self.service.validate(AddressRequest(raw_address_text="1456 Heritage Court Fall River NS"))
        self.assertEqual(result["decision"], "accept")
        self.assertEqual(result["hints"]["parser_disagreement"], True)
        self.assertEqual(result["hints"]["hard_parser_disagreement"], False)
        self.assertEqual(result["hints"]["parser_disagreement_kind"], "unit_only")
        self.assertEqual(
            result["reason"],
            "Single-unit residential address is complete enough to accept despite soft unit-only disagreement.",
        )

    @patch.object(AddressPlatformService, "parse")
    def test_validate_enriches_multi_unit_on_soft_unit_only_disagreement(self, mock_parse):
        mock_parse.return_value = {
            "candidates": [
                {
                    "street_number": "200",
                    "street_name": "MAIN ST",
                    "unit_number": None,
                    "city": "HALIFAX",
                    "province": "NS",
                    "postal_code": None,
                    "score": 0.72,
                    "parser_name": "hybrid_canada",
                    "parsed": {
                        "street_number": "200",
                        "street_name": "MAIN ST",
                        "unit_number": None,
                        "city": "HALIFAX",
                        "province": "NS",
                        "postal_code": None,
                        "feature_vector": {"pattern": "plain_house"},
                    },
                },
                {
                    "street_number": "200",
                    "street_name": "MAIN ST",
                    "unit_number": "304",
                    "city": "HALIFAX",
                    "province": "NS",
                    "postal_code": None,
                    "score": 0.69,
                    "parser_name": "libpostal",
                    "parsed": {
                        "street_number": "200",
                        "street_name": "MAIN ST",
                        "unit_number": "304",
                        "city": "HALIFAX",
                        "province": "NS",
                        "postal_code": None,
                        "feature_vector": {"pattern": "plain_house"},
                    },
                },
            ]
        }
        with patch("addressforge.api.server.infer_structure_type", return_value="multi_unit"):
            result = self.service.validate(AddressRequest(raw_address_text="200 Main St Halifax NS"))
        self.assertEqual(result["decision"], "enrich")
        self.assertEqual(result["hints"]["parser_disagreement"], True)
        self.assertEqual(result["hints"]["hard_parser_disagreement"], False)
        self.assertEqual(result["hints"]["parser_disagreement_kind"], "unit_only")
        self.assertEqual(
            result["reason"],
            "Multi-unit residential address is likely valid, but unit details may be recovered from soft disagreement.",
        )


if __name__ == "__main__":
    unittest.main()
