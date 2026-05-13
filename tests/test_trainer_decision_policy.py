from __future__ import annotations

import unittest

from addressforge.learning.trainer import _apply_decision_policy_calibration_proposal


class TestTrainerDecisionPolicyCalibration(unittest.TestCase):
    def test_apply_decision_policy_calibration_proposal_updates_supported_thresholds(self):
        policy = {
            "assist_accept_score_threshold": 0.70,
            "assist_accept_parse_score_threshold": 0.68,
            "assist_review_score_threshold": 0.55,
            "assist_review_parse_score_threshold": 0.80,
            "assist_review_reference_score_threshold": 0.60,
        }
        proposal = {
            "status": "needs_more_assist_calibration",
            "source_model_name": "canada_default",
            "source_model_version": "v_prev",
            "recommended_changes": [
                {
                    "threshold": "assist_accept_score_threshold",
                    "direction": "increase",
                    "step": 0.02,
                    "reason": "reduce aggressive accept recoveries",
                },
                {
                    "threshold": "assist_review_parse_score_threshold",
                    "direction": "decrease",
                    "step": 0.02,
                    "reason": "narrow review escalation",
                },
                {
                    "threshold": "reject_override",
                    "direction": "hold_disabled",
                    "step": 0.0,
                    "reason": "keep reject override disabled",
                },
            ],
        }

        applied = _apply_decision_policy_calibration_proposal(policy, proposal)

        self.assertTrue(applied["applied"])
        self.assertEqual(applied["source_model_version"], "v_prev")
        self.assertEqual(policy["assist_accept_score_threshold"], 0.72)
        self.assertEqual(policy["assist_review_parse_score_threshold"], 0.78)
        self.assertEqual(len(applied["changes"]), 2)


if __name__ == "__main__":
    unittest.main()
