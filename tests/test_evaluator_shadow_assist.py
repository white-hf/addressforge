from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import unittest

from addressforge.learning.evaluator import run_baseline_evaluation
from addressforge.learning.evaluator import (
    _building_type_assist_summary,
    _decision_assist_rollout_readiness,
    _decision_policy_calibration_proposal,
    _decision_shadow_assist_summary,
    _decision_threshold_tuning_hints,
)


class TestEvaluatorShadowAssist(unittest.TestCase):
    def test_building_type_assist_summary_tracks_transitions_and_gold_match(self):
        rows = [
            {
                "source_id": "1",
                "raw_address_text": "A",
                "label_json": '{"building_type":"multi_unit"}',
                "building_type": "single_unit",
                "ml_building_type": "multi_unit",
                "bt_confidence": 0.95,
                "bt_assist_enabled": True,
                "assist_policy_mode": "assist_trial",
                "bt_allowed_transitions": [["single_unit", "multi_unit"], ["multi_unit", "single_unit"]],
                "bt_override_applied": True,
            },
            {
                "source_id": "2",
                "raw_address_text": "B",
                "label_json": '{"building_type":"single_unit"}',
                "building_type": "multi_unit",
                "ml_building_type": "single_unit",
                "bt_confidence": 0.91,
                "bt_assist_enabled": True,
                "assist_policy_mode": "assist_trial",
                "bt_allowed_transitions": [["single_unit", "multi_unit"], ["multi_unit", "single_unit"]],
                "bt_override_applied": False,
            },
            {
                "source_id": "3",
                "raw_address_text": "C",
                "label_json": '{"building_type":"commercial"}',
                "building_type": "single_unit",
                "ml_building_type": "commercial",
                "bt_confidence": 0.99,
                "bt_assist_enabled": True,
                "assist_policy_mode": "assist_trial",
                "bt_allowed_transitions": [["single_unit", "multi_unit"], ["multi_unit", "single_unit"]],
                "bt_override_applied": False,
            },
        ]

        summary = _building_type_assist_summary(rows)
        self.assertEqual(summary["compared"], 3)
        self.assertEqual(summary["eligible_count"], 2)
        self.assertEqual(summary["applied_count"], 1)
        self.assertAlmostEqual(summary["gold_match_rate"], 1.0)
        self.assertEqual(summary["transition_counts"]["single_unit->multi_unit"], 1)
        self.assertEqual(summary["transition_counts"]["multi_unit->single_unit"], 1)
        self.assertEqual(summary["transition_counts"]["single_unit->commercial"], 1)
        self.assertEqual(summary["eligible_transition_counts"]["single_unit->multi_unit"], 1)
        self.assertEqual(summary["eligible_transition_counts"]["multi_unit->single_unit"], 1)
        self.assertNotIn("single_unit->commercial", summary["eligible_transition_counts"])
        self.assertEqual(summary["applied_transition_counts"]["single_unit->multi_unit"], 1)

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
        proposal = _decision_policy_calibration_proposal(tuning, readiness)
        self.assertEqual(proposal["status"], "shadow_only")
        self.assertFalse(proposal["apply_now"])
        thresholds = {item["threshold"] for item in proposal["recommended_changes"]}
        self.assertIn("assist_accept_score_threshold", thresholds)
        self.assertIn("reject_override", thresholds)

    def test_run_baseline_evaluation_uses_runtime_bundle_validation(self):
        fake_rows = [
            {
                "gold_label_id": 1,
                "source_id": "1",
                "label_json": '{"decision":"accept","building_type":"multi_unit","unit_number":"5"}',
                "raw_address_text": "1200 Main St Apt 5 Halifax NS",
                "city": "Halifax",
                "province": "NS",
                "postal_code": "B3H 0A1",
                "country_code": "CA",
                "decision": "accept",
                "building_type": "multi_unit",
                "suggested_unit_number": "5",
            }
        ]
        model_service = MagicMock()
        reranker_service = MagicMock()
        model_service.describe_runtime.return_value = {"model_path": "runtime/models/default_canada_default_catboost_canada_default_v1.pkl"}
        reranker_service.describe_runtime.return_value = {"model_path": "runtime/models/reranker.cbm"}
        model_service.validate = MagicMock()
        model_service.validate.return_value = {
            "decision": "accept",
            "building_type": "multi_unit",
            "suggested_unit_number": "5",
            "ml_decision": {"ml_decision": "accept", "ml_score": 0.93, "status": "success"},
            "shadow_assist": {
                "ml_building_type": "multi_unit",
                "bt_confidence": 0.93,
                "bt_assist_enabled": True,
                "bt_allowed_transitions": [["single_unit", "multi_unit"], ["multi_unit", "single_unit"]],
                "bt_override_applied": False,
                "assist_policy_mode": "assist_trial",
            },
            "reranker_impact_detected": False,
        }

        with patch.dict(
            "os.environ",
            {
                "ADDRESSFORGE_SKIP_CANADA_BENCHMARK": "1",
                "ADDRESSFORGE_SKIP_REPLAY_ON_EVAL": "1",
            },
            clear=False,
        ), patch(
            "addressforge.learning.evaluator.create_run",
            return_value=123,
        ), patch(
            "addressforge.learning.evaluator.finish_run",
            return_value=None,
        ), patch(
            "addressforge.learning.evaluator.fetch_all",
            side_effect=[[{"cnt": 1}], [{"cnt": 1}], fake_rows, [{"decision": "accept", "building_type": "multi_unit", "suggested_unit_number": "5"}]],
        ), patch(
            "addressforge.learning.evaluator.count_gold_labels", return_value=1
        ), patch(
            "addressforge.learning.evaluator.get_active_model",
            return_value={"model_name": "canada_default", "model_version": "canada_default_v1", "metrics_json": {"release_benchmark": {"decision_f1": 0.5}}},
        ), patch(
            "addressforge.learning.evaluator.get_model",
            return_value={
                "metrics_json": {
                    "manifest_schema_version": "1.0",
                    "runtime_bundle_id": "default:canada_default:canada_default_v1",
                }
            },
        ), patch(
            "addressforge.learning.evaluator.register_model_version",
            return_value={"model_name": "canada_default", "model_version": "canada_default_v1"},
        ), patch(
            "addressforge.learning.evaluator._predict_gold_rows_with_runtime",
            return_value=fake_rows,
        ), patch(
            "addressforge.learning.evaluator._resolve_model_runtime",
            return_value={"ok": True, "profile": "base_canada", "parsers": ("simple_rule",), "decision_policy": {}, "model_service": model_service, "reranker_service": reranker_service, "manifest": {}},
        ):
            artifact = run_baseline_evaluation(workspace_name="default", model_name="canada_default", model_version="canada_default_v1", dataset_name="gold_v20260517")

        self.assertEqual(artifact["metric_name"], "decision_f1")
        self.assertEqual(artifact["metrics_json"]["manifest_schema_version"], "1.0")
        self.assertEqual(artifact["metrics_json"]["runtime_identity"]["decision_model"]["model_path"], "runtime/models/default_canada_default_catboost_canada_default_v1.pkl")
        self.assertEqual(model_service.describe_runtime.call_count, 1)
        self.assertEqual(reranker_service.describe_runtime.call_count, 1)

    def test_to_count_handles_list_mismatches(self):
        from addressforge.learning.evaluator import _to_count

        self.assertEqual(_to_count([{"raw_id": 1}, {"raw_id": 2}]), 2)
        self.assertEqual(_to_count({"a": 1, "b": 2}), 2)
        self.assertEqual(_to_count(None), 0)
        self.assertEqual(_to_count("3"), 3)


if __name__ == "__main__":
    unittest.main()
