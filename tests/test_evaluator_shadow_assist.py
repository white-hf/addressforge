from __future__ import annotations

import unittest

from addressforge.learning.evaluator import _decision_shadow_assist_summary


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
            },
        ]

        summary = _decision_shadow_assist_summary(rows)
        self.assertEqual(summary["compared"], 3)
        self.assertEqual(summary["model_available"], 3)
        self.assertAlmostEqual(summary["heuristic"]["f1"], 0.3333)
        self.assertAlmostEqual(summary["ml_shadow"]["f1"], 1.0)
        self.assertAlmostEqual(summary["shadow_advantage"], 0.6667)
        self.assertAlmostEqual(summary["disagreement_rate"], 0.6667)
        self.assertEqual(summary["bucket_counts"]["MODEL_MORE_AGGRESSIVE_ACCEPT"], 1)
        self.assertEqual(summary["bucket_counts"]["MODEL_REJECT_ESCALATION"], 1)
        self.assertEqual(len(summary["disagreement_samples"]), 2)


if __name__ == "__main__":
    unittest.main()
