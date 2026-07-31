from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from addressforge.services.replay_service import (
    _load_model_runtime,
    _persist_replay_evidence,
    get_release_readiness_report,
    run_historical_replay,
)


class TestReplayRuntime(unittest.TestCase):
    @patch("addressforge.services.replay_service.build_runtime_bundle_from_model_row")
    @patch("addressforge.services.replay_service.fetch_all")
    def test_load_model_runtime_uses_governed_shared_bundle_loader(
        self,
        mock_fetch_all,
        mock_build_runtime_bundle,
    ):
        model_row = {
            "model_id": 12,
            "workspace_name": "default",
            "model_name": "canada_default",
            "model_version": "v_test",
        }
        mock_fetch_all.return_value = [model_row]
        sentinel_service = object()
        sentinel_reranker = object()
        mock_build_runtime_bundle.return_value = {
            "ok": True,
            "profile": "runtime_profile_v2",
            "parsers": ("hybrid_canada", "libpostal"),
            "decision_policy": {"high_confidence_accept_threshold": 0.91},
            "model_service": sentinel_service,
            "reranker_service": sentinel_reranker,
        }

        runtime = _load_model_runtime("default", "v_test")

        self.assertTrue(runtime["ok"])
        self.assertEqual(runtime["profile"], "runtime_profile_v2")
        self.assertEqual(runtime["parsers"], ("hybrid_canada", "libpostal"))
        self.assertEqual(runtime["decision_policy"], {"high_confidence_accept_threshold": 0.91})
        self.assertIs(runtime["model_service"], sentinel_service)
        self.assertIs(runtime["reranker_service"], sentinel_reranker)
        mock_build_runtime_bundle.assert_called_once_with(model_row, mode="governed")

    @patch("addressforge.services.replay_service.db_cursor")
    def test_persist_replay_evidence_writes_summary_and_every_row(
        self,
        mock_db_cursor,
    ):
        connection = MagicMock()
        cursor = MagicMock()
        cursor.lastrowid = 88
        mock_db_cursor.return_value.__enter__.return_value = (connection, cursor)
        evidence_rows = [
            (
                "default", 123, 1,
                "accept", "single_unit", None,
                "accept", "single_unit", None,
                "accept", "single_unit", None,
                1, 1, 1, 0, 0, 0,
                "success", None, "{}", "{}", "{}",
            ),
            (
                "default", 123, 2,
                "review", "multi_unit", "5",
                None, None, None,
                None, None, None,
                0, 0, 0, 1, 0, 0,
                "failed", "inference error", "{}", None, None,
            ),
        ]

        replay_id = _persist_replay_evidence(
            workspace_name="default",
            run_id=123,
            candidate_model={
                "model_id": 51,
                "model_name": "canada_candidate",
                "model_version": "v_candidate",
            },
            active_model={"model_id": 1},
            requested_count=2,
            processed_count=1,
            failure_count=1,
            disagreement_count=0,
            decision_match_rate=1.0,
            building_type_match_rate=1.0,
            unit_number_match_rate=1.0,
            status="completed_with_failures",
            runtime_identity={"candidate": {"id": 51}, "active": {"id": 1}},
            evidence_rows=evidence_rows,
        )

        self.assertEqual(replay_id, 88)
        cursor.executemany.assert_called_once()
        self.assertEqual(cursor.executemany.call_args.args[1], evidence_rows)
        connection.commit.assert_called_once_with()

    @patch("addressforge.services.replay_service._persist_replay_evidence")
    @patch("addressforge.services.replay_service.finish_run")
    @patch("addressforge.services.replay_service.create_run", return_value=123)
    @patch("addressforge.services.replay_service.get_active_model")
    @patch("addressforge.services.replay_service._load_model_runtime")
    @patch("addressforge.services.replay_service.fetch_all")
    def test_replay_persists_success_and_failure_as_row_evidence(
        self,
        mock_fetch_all,
        mock_load_runtime,
        mock_get_active_model,
        _mock_create_run,
        mock_finish_run,
        mock_persist,
    ):
        candidate_model = {
            "model_id": 51,
            "model_name": "canada_candidate",
            "model_version": "v_candidate",
        }
        active_model = {
            "model_id": 1,
            "model_name": "canada_default",
            "model_version": "v_active",
        }
        records = [
            {
                "raw_id": 10,
                "raw_address_text": "10 Main St",
                "city": "Halifax",
                "province": "NS",
                "postal_code": "B3H 1A1",
                "current_decision": "accept",
                "current_building_type": "single_unit",
                "current_unit_number": None,
            },
            {
                "raw_id": 11,
                "raw_address_text": "11 Main St Apt 5",
                "city": "Halifax",
                "province": "NS",
                "postal_code": "B3H 1A2",
                "current_decision": "review",
                "current_building_type": "multi_unit",
                "current_unit_number": "5",
            },
        ]
        mock_fetch_all.side_effect = [[candidate_model], records]
        mock_get_active_model.return_value = active_model
        runtime = {
            "ok": True,
            "profile": "base_canada",
            "parsers": ("hybrid_canada",),
            "decision_policy": {},
            "model_service": MagicMock(),
            "reranker_service": MagicMock(),
            "runtime_identity": {"mode": "governed"},
        }
        mock_load_runtime.side_effect = [runtime, runtime]
        mock_persist.return_value = 88

        candidate_service = MagicMock()
        active_service = MagicMock()
        candidate_service.validate.side_effect = [
            {
                "decision": "review",
                "building_type": "single_unit",
                "suggested_unit_number": None,
            },
            RuntimeError("candidate inference failed"),
        ]
        active_service.validate.return_value = {
            "decision": "accept",
            "building_type": "single_unit",
            "suggested_unit_number": None,
        }

        with (
            patch(
                "addressforge.api.server.AddressPlatformService",
                side_effect=[candidate_service, active_service],
            ),
            patch("addressforge.api.server.AddressRequest", side_effect=lambda **kwargs: kwargs),
        ):
            result = run_historical_replay(
                workspace_name="default",
                candidate_version="v_candidate",
                limit=2,
            )

        self.assertEqual(result["status"], "completed_with_failures")
        self.assertEqual(result["requested"], 2)
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["failures"], 1)
        self.assertEqual(result["mismatch_count"], 1)
        persisted_rows = mock_persist.call_args.kwargs["evidence_rows"]
        self.assertEqual(len(persisted_rows), 2)
        self.assertEqual(persisted_rows[0][18], "success")
        self.assertEqual(persisted_rows[1][18], "failed")
        self.assertIn("candidate inference failed", persisted_rows[1][19])
        mock_finish_run.assert_called_once()

    @patch("addressforge.services.replay_service.build_release_readiness_report")
    @patch("addressforge.services.replay_service.fetch_all")
    def test_business_readiness_uses_same_governed_gate_as_promotion(
        self,
        mock_fetch_all,
        mock_build_readiness,
    ):
        candidate = {"model_id": 51, "status": "evaluated", "is_default": 0}
        mock_fetch_all.return_value = [candidate]
        mock_build_readiness.return_value = {
            "status": "blocked",
            "ready": False,
            "blockers": [{"code": "replay_reliability"}],
        }

        result = get_release_readiness_report("default")

        self.assertFalse(result["ready"])
        mock_build_readiness.assert_called_once_with(candidate)


if __name__ == "__main__":
    unittest.main()
