from __future__ import annotations

import unittest

from addressforge.learning.evaluator import (
    _decision_assist_rollout_readiness,
    _decision_shadow_assist_summary,
    _decision_threshold_tuning_hints,
)


class TestEvaluatorShadowAssist(unittest.TestCase):
    def test_decision_shadow_assist_summary_tracks_advantage_and_buckets(self):
        rows = [
            {
                "source_id": "1",
                "raw_address_text": "A",
                "label_json": '{"decision":"accept"}',
                "heuristic_decision": "review",
                "ml_shadow_decision": "accept",
                "ml_shadow_score": 0.82,
                "ml_shadow_status": "success",
                "shadow_disagreement_reason": "model_more_aggressive_accept",
                "assist_eligible": True,
                "assist_recommended_decision": "accept",
                "assist_guard_reason": "eligible_accept_recovery",
            },
            {
                "source_id": "2",
                "raw_address_text": "B",
                "label_json": '{"decision":"review"}',
                "heuristic_decision": "review",
                "ml_shadow_decision": "review",
                "ml_shadow_score": 0.77,
                "ml_shadow_status": "success",
                "shadow_disagreement_reason": "agree",
                "assist_eligible": False,
                "assist_recommended_decision": None,
                "assist_guard_reason": "agree_with_heuristic",
            },
            {
                "source_id": "3",
                "raw_address_text": "C",
                "label_json": '{"decision":"reject"}',
                "heuristic_decision": "accept",
                "ml_shadow_decision": "reject",
                "ml_shadow_score": 0.66,
                "ml_shadow_status": "success",
                "shadow_disagreement_reason": "model_reject_escalation",
                "assist_eligible": False,
                "assist_recommended_decision": None,
                "assist_guard_reason": "reject_override_not_enabled",
            },
        ]

        summary = _decision_shadow_assist_summary(rows)
        self.assertEqual(summary["compared"], 3)
        self.assertEqual(summary["model_available"], 3)
        self.assertAlmostEqual(summary["heuristic"]["f1"], 0.3333)
        self.assertAlmostEqual(summary["ml_shadow"]["f1"], 1.0)
        self.assertAlmostEqual(summary["assist_trial"]["f1"], 0.6667)
        self.assertAlmostEqual(summary["shadow_advantage"], 0.6667)
        self.assertAlmostEqual(summary["assist_trial_advantage"], 0.3334)
        self.assertAlmostEqual(summary["disagreement_rate"], 0.6667)
        self.assertEqual(summary["bucket_counts"]["MODEL_MORE_AGGRESSIVE_ACCEPT"], 1)
        self.assertEqual(summary["bucket_counts"]["MODEL_REJECT_ESCALATION"], 1)
        self.assertEqual(summary["assist_readiness"]["eligible_count"], 1)
        self.assertEqual(summary["assist_readiness"]["recommended_decision_counts"]["accept"], 1)
        self.assertEqual(summary["assist_readiness"]["guard_reason_counts"]["eligible_accept_recovery"], 1)
        self.assertAlmostEqual(summary["assist_readiness"]["gold_match_rate"], 1.0)
        self.assertEqual(len(summary["disagreement_samples"]), 2)

        readiness = _decision_assist_rollout_readiness(summary)
        self.assertEqual(readiness["status"], "shadow_only")
        self.assertTrue(readiness["checks"]["shadow_beats_heuristic"])
        self.assertFalse(readiness["checks"]["assist_trial_not_worse_than_shadow"])
        self.assertFalse(readiness["checks"]["assist_gold_match_rate_sufficient"])
        tuning = _decision_threshold_tuning_hints(summary, readiness)
        self.assertEqual(tuning["status"], "shadow_only")
        self.assertEqual(tuning["next_action"], "hold shadow-only and continue boundary calibration")
        buckets = {item["target_bucket"] for item in tuning["hints"]}
        self.assertIn("MODEL_MORE_AGGRESSIVE_ACCEPT", buckets)
        self.assertIn("MODEL_REJECT_ESCALATION", buckets)


if __name__ == "__main__":
    unittest.main()
