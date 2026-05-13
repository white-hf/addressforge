from __future__ import annotations

import unittest

from addressforge.api.server import AddressPlatformService


class DummyModelService:
    def predict_decision(self, *args, **kwargs):  # pragma: no cover - not used in direct policy test
        return {"status": "no_model", "ml_score": 0.0}


class TestShadowAssistPolicy(unittest.TestCase):
    def setUp(self):
        self.service = AddressPlatformService(model_service=DummyModelService())

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


if __name__ == "__main__":
    unittest.main()
