import asyncio
import unittest
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestCleaningRoute(unittest.TestCase):
    @patch("addressforge.api.routes.cleaning.enqueue_cleaning")
    @patch("addressforge.core.common.db_cursor")
    def test_reclean_reviews_rolls_back_to_first_review_row_only(self, mock_db_cursor, mock_enqueue):
        from addressforge.api.routes.cleaning import CleaningRequest, reclean_reviews

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"min_id": 123}
        mock_cursor.rowcount = 7
        mock_db_cursor.return_value.__enter__.return_value = (mock_conn, mock_cursor)
        mock_enqueue.return_value = {"job_id": 99, "job_kind": "cleaning_once"}

        request = CleaningRequest(workspace_name="default", batch_size=500, requested_by="test", notes="")
        result = asyncio.run(reclean_reviews(request))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["affected_records"], 7)
        self.assertEqual(result["rolled_back_to"], 123)
        self.assertEqual(result["job"]["job_id"], 99)

        execute_calls = mock_cursor.execute.call_args_list
        self.assertIn("SELECT MIN(acr.raw_id) as min_id", execute_calls[0].args[0])
        self.assertIn("JOIN raw_address_record rar", execute_calls[0].args[0])
        self.assertIn("UPDATE address_cleaning_result acr", execute_calls[1].args[0])
        self.assertIn('UPDATE control_setting SET setting_value = %s', execute_calls[2].args[0])
        self.assertEqual(execute_calls[2].args[1], ("122", "default"))

    @patch("addressforge.api.routes.cleaning.enqueue_cleaning")
    @patch("addressforge.core.common.db_cursor")
    def test_reclean_reviews_skips_cursor_rewind_when_no_review_rows(self, mock_db_cursor, mock_enqueue):
        from addressforge.api.routes.cleaning import CleaningRequest, reclean_reviews

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"min_id": None}
        mock_cursor.rowcount = 0
        mock_db_cursor.return_value.__enter__.return_value = (mock_conn, mock_cursor)
        mock_enqueue.return_value = {"job_id": 101, "job_kind": "cleaning_once"}

        request = CleaningRequest(workspace_name="default", batch_size=500, requested_by="test", notes="")
        result = asyncio.run(reclean_reviews(request))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["affected_records"], 0)
        self.assertIsNone(result["rolled_back_to"])
        execute_sql = [call.args[0] for call in mock_cursor.execute.call_args_list]
        self.assertEqual(sum('UPDATE control_setting SET setting_value = %s' in sql for sql in execute_sql), 0)

    @patch("addressforge.api.routes.cleaning.enqueue_cleaning")
    @patch("addressforge.core.common.db_cursor")
    def test_reclean_reviews_supports_source_and_batch_filters(self, mock_db_cursor, mock_enqueue):
        from addressforge.api.routes.cleaning import CleaningRequest, reclean_reviews

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"min_id": 456}
        mock_cursor.rowcount = 3
        mock_db_cursor.return_value.__enter__.return_value = (mock_conn, mock_cursor)
        mock_enqueue.return_value = {"job_id": 102, "job_kind": "cleaning_once"}

        request = CleaningRequest(
            workspace_name="default",
            batch_size=250,
            requested_by="test",
            notes="",
            source_name="third_party",
            batch_id="batch-2026-05-15",
        )
        result = asyncio.run(reclean_reviews(request))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["affected_records"], 3)
        self.assertEqual(result["source_name"], "third_party")
        self.assertEqual(result["batch_id"], "batch-2026-05-15")

        execute_calls = mock_cursor.execute.call_args_list
        self.assertIn("JOIN raw_address_record rar", execute_calls[0].args[0])
        self.assertIn("rar.source_name = %s", execute_calls[0].args[0])
        self.assertIn('JSON_UNQUOTE(JSON_EXTRACT(rar.source_payload, "$.batch_id")) = %s', execute_calls[0].args[0])
        self.assertEqual(execute_calls[0].args[1], ("default", "third_party", "batch-2026-05-15"))
        self.assertIn("UPDATE address_cleaning_result acr", execute_calls[1].args[0])
        self.assertEqual(execute_calls[1].args[1], ("default", "third_party", "batch-2026-05-15"))

    @patch("addressforge.core.common.fetch_all")
    @patch("addressforge.api.server.AddressPlatformService")
    def test_preview_reclean_reviews_returns_decision_breakdown(self, mock_service_cls, mock_fetch_all):
        from addressforge.api.routes.cleaning import CleaningRequest, preview_reclean_reviews

        mock_fetch_all.return_value = [
            {
                "raw_id": 1001,
                "raw_address_text": "200 Main St Halifax NS",
                "source_name": "third_party",
                "batch_id": "batch-2026-05-15",
            },
            {
                "raw_id": 1002,
                "raw_address_text": "1456 Heritage Court Fall River NS",
                "source_name": "third_party",
                "batch_id": "batch-2026-05-15",
            },
        ]
        mock_service = MagicMock()
        mock_service.validate.side_effect = [
            {"decision": "enrich", "reason": "unit missing", "building_type": "multi_unit", "suggested_unit_number": None},
            {"decision": "accept", "reason": "structure complete", "building_type": "single_unit", "suggested_unit_number": None},
        ]
        mock_service_cls.return_value = mock_service

        request = CleaningRequest(
            workspace_name="default",
            source_name="third_party",
            batch_id="batch-2026-05-15",
            preview_limit=50,
        )
        result = asyncio.run(preview_reclean_reviews(request))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["sampled_rows"], 2)
        self.assertEqual(result["decision_counts"], {"enrich": 1, "accept": 1})
        self.assertEqual(result["transition_counts"], {"review->enrich": 1, "review->accept": 1})
        self.assertEqual(result["projected_recovery_count"], 2)
        self.assertEqual(result["projected_remaining_review_count"], 0)
        self.assertEqual(result["projected_recovery_rate"], 1.0)
        self.assertEqual(result["source_name"], "third_party")
        self.assertEqual(result["batch_id"], "batch-2026-05-15")
        self.assertEqual(len(result["samples"]), 2)

        sql = mock_fetch_all.call_args.args[0]
        params = mock_fetch_all.call_args.args[1]
        self.assertIn("JOIN raw_address_record rar", sql)
        self.assertIn("rar.source_name = %s", sql)
        self.assertIn('JSON_UNQUOTE(JSON_EXTRACT(rar.source_payload, "$.batch_id")) = %s', sql)
        self.assertEqual(params, ("default", "third_party", "batch-2026-05-15"))

    @patch("addressforge.pipelines.cleaning.db_cursor")
    def test_upsert_stage_result_accepts_string_parser_json(self, mock_db_cursor):
        from addressforge.pipelines.cleaning import _upsert_stage_result

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db_cursor.return_value.__enter__.return_value = (mock_conn, mock_cursor)

        parse_result = '{"best_candidate": {"parsed": {"street_name": "MAIN ST"}}}'
        validation_result = '{"decision": "review", "building_type": "single_unit", "canonical": {}, "reference": {}}'

        _upsert_stage_result(
            "default",
            {"raw_id": 123, "raw_address_text": "123 Main St Halifax NS"},
            checkpoint_stage="publish",
            checkpoint_status="completed",
            parse_result=parse_result,
            validation_result=validation_result,
        )

        execute_args = mock_cursor.execute.call_args.args[1]
        self.assertIsNotNone(execute_args[11])  # parser_json payload
        self.assertIsNotNone(execute_args[12])  # validation_json payload

    @patch("addressforge.core.common.fetch_all")
    def test_reclean_reviews_evidence_returns_current_distribution(self, mock_fetch_all):
        from addressforge.api.routes.cleaning import CleaningRequest, reclean_reviews_evidence

        mock_fetch_all.side_effect = [
            [
                {"decision": "accept", "cnt": 8},
                {"decision": "enrich", "cnt": 2},
                {"decision": "review", "cnt": 1},
            ],
            [
                {"reason": "Parser confidence is moderate; review is safer.", "cnt": 1},
            ],
            [
                {"building_type": "single_unit", "cnt": 1},
            ],
        ]

        request = CleaningRequest(
            workspace_name="default",
            source_name="third_party",
            batch_id="batch-2026-05-15",
        )
        result = asyncio.run(reclean_reviews_evidence(request))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["total_rows"], 11)
        self.assertEqual(result["decision_counts"], {"accept": 8, "enrich": 2, "review": 1})
        self.assertEqual(result["review_count"], 1)
        self.assertEqual(result["recovered_count"], 10)
        self.assertEqual(result["review_rate"], 0.0909)
        self.assertEqual(result["recovered_rate"], 0.9091)
        self.assertEqual(
            result["remaining_review_reason_counts"],
            {"Parser confidence is moderate; review is safer.": 1},
        )
        self.assertEqual(result["remaining_review_building_type_counts"], {"single_unit": 1})

        sql = mock_fetch_all.call_args_list[0].args[0]
        params = mock_fetch_all.call_args_list[0].args[1]
        self.assertIn("GROUP BY COALESCE(acr.decision, 'pending')", sql)
        self.assertIn("rar.source_name = %s", sql)
        self.assertIn('JSON_UNQUOTE(JSON_EXTRACT(rar.source_payload, "$.batch_id")) = %s', sql)
        self.assertEqual(params, ("default", "third_party", "batch-2026-05-15"))

    @patch("addressforge.core.common.fetch_all")
    def test_reclean_review_opportunities_returns_top_batches(self, mock_fetch_all):
        from addressforge.api.routes.cleaning import CleaningRequest, reclean_review_opportunities

        mock_fetch_all.return_value = [
            {
                "source_name": "third_party",
                "batch_id": "batch-a",
                "total_rows": 100,
                "review_count": 25,
                "accept_count": 70,
                "enrich_count": 3,
                "pending_count": 2,
            },
            {
                "source_name": "third_party",
                "batch_id": "batch-b",
                "total_rows": 80,
                "review_count": 10,
                "accept_count": 60,
                "enrich_count": 5,
                "pending_count": 5,
            },
        ]

        request = CleaningRequest(workspace_name="default", source_name="third_party", preview_limit=10)
        result = asyncio.run(reclean_review_opportunities(request))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["limit"], 10)
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["batch_id"], "batch-a")
        self.assertEqual(result["items"][0]["review_rate"], 0.25)

        sql = mock_fetch_all.call_args.args[0]
        params = mock_fetch_all.call_args.args[1]
        self.assertIn("GROUP BY rar.source_name", sql)
        self.assertIn("HAVING review_count > 0", sql)
        self.assertIn("rar.source_name = %s", sql)
        self.assertEqual(params, ("default", "third_party"))

    @patch("addressforge.core.common.fetch_all")
    def test_review_residual_buckets_returns_reason_and_hint_counts(self, mock_fetch_all):
        from addressforge.api.routes.cleaning import CleaningRequest, review_residual_buckets

        mock_fetch_all.side_effect = [
            [{"reason": "Parser confidence is moderate; review is safer.", "cnt": 7}],
            [{"building_type": "single_unit", "cnt": 5}],
            [{"disagreement_kind": "base_address", "cnt": 3}],
            [{"reference_gap_reason": "NO_REFERENCE_CANDIDATE", "cnt": 6}],
        ]

        request = CleaningRequest(
            workspace_name="default",
            source_name="third_party",
            batch_id="batch-2026-05-15",
            preview_limit=5,
        )
        result = asyncio.run(review_residual_buckets(request))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["reason_counts"], {"Parser confidence is moderate; review is safer.": 7})
        self.assertEqual(result["building_type_counts"], {"single_unit": 5})
        self.assertEqual(result["parser_disagreement_kind_counts"], {"base_address": 3})
        self.assertEqual(result["reference_gap_reason_counts"], {"NO_REFERENCE_CANDIDATE": 6})
        self.assertEqual(result["batch_id"], "batch-2026-05-15")

        first_sql = mock_fetch_all.call_args_list[0].args[0]
        first_params = mock_fetch_all.call_args_list[0].args[1]
        self.assertIn("acr.decision = 'review'", first_sql)
        self.assertIn("rar.source_name = %s", first_sql)
        self.assertIn('JSON_UNQUOTE(JSON_EXTRACT(rar.source_payload, "$.batch_id")) = %s', first_sql)
        self.assertEqual(first_params, ("default", "third_party", "batch-2026-05-15"))

    @patch("addressforge.api.routes.cleaning.enqueue_cleaning")
    @patch("addressforge.core.common.db_cursor")
    @patch("addressforge.core.common.fetch_all")
    def test_reclean_top_review_opportunities_resets_selected_batches(self, mock_fetch_all, mock_db_cursor, mock_enqueue):
        from addressforge.api.routes.cleaning import CleaningRequest, reclean_top_review_opportunities

        mock_fetch_all.return_value = [
            {
                "source_name": "third_party",
                "batch_id": "batch-a",
                "total_rows": 100,
                "review_count": 25,
                "accept_count": 70,
                "enrich_count": 3,
                "pending_count": 2,
            },
            {
                "source_name": "third_party",
                "batch_id": "batch-b",
                "total_rows": 80,
                "review_count": 10,
                "accept_count": 60,
                "enrich_count": 5,
                "pending_count": 5,
            },
        ]
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"min_id": 321}
        mock_cursor.rowcount = 19
        mock_db_cursor.return_value.__enter__.return_value = (mock_conn, mock_cursor)
        mock_enqueue.return_value = {"job_id": 200, "job_kind": "cleaning_once"}

        request = CleaningRequest(
            workspace_name="default",
            source_name="third_party",
            batch_size=400,
            opportunity_limit=2,
            requested_by="test",
        )
        result = asyncio.run(reclean_top_review_opportunities(request))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["affected_records"], 19)
        self.assertEqual(result["rolled_back_to"], 321)
        self.assertEqual(len(result["processed_batches"]), 2)
        self.assertEqual(result["processed_batches"][0]["batch_id"], "batch-a")
        self.assertEqual(result["job"]["job_id"], 200)

        execute_calls = mock_cursor.execute.call_args_list
        self.assertIn("SELECT MIN(acr.raw_id) as min_id", execute_calls[0].args[0])
        self.assertIn("UPDATE address_cleaning_result acr", execute_calls[1].args[0])
        self.assertIn('UPDATE control_setting SET setting_value = %s', execute_calls[2].args[0])
        self.assertIn("rar.source_name = %s", execute_calls[0].args[0])
        self.assertIn('JSON_UNQUOTE(JSON_EXTRACT(rar.source_payload, "$.batch_id")) = %s', execute_calls[0].args[0])
        self.assertEqual(
            execute_calls[0].args[1],
            ("default", "third_party", "batch-a", "third_party", "batch-b"),
        )

    @patch("addressforge.api.server.AddressPlatformService")
    @patch("addressforge.core.common.fetch_all")
    def test_preview_top_review_opportunities_aggregates_selected_batches(self, mock_fetch_all, mock_service_cls):
        from addressforge.api.routes.cleaning import CleaningRequest, preview_top_review_opportunities

        mock_fetch_all.side_effect = [
            [
                {
                    "source_name": "third_party",
                    "batch_id": "batch-a",
                    "total_rows": 100,
                    "review_count": 25,
                    "accept_count": 70,
                    "enrich_count": 3,
                    "pending_count": 2,
                },
                {
                    "source_name": "third_party",
                    "batch_id": "batch-b",
                    "total_rows": 80,
                    "review_count": 10,
                    "accept_count": 60,
                    "enrich_count": 5,
                    "pending_count": 5,
                },
            ],
            [
                {
                    "raw_id": 1001,
                    "raw_address_text": "200 Main St Halifax NS",
                    "source_name": "third_party",
                    "batch_id": "batch-a",
                },
                {
                    "raw_id": 1002,
                    "raw_address_text": "1456 Heritage Court Fall River NS",
                    "source_name": "third_party",
                    "batch_id": "batch-b",
                },
            ],
        ]
        mock_service = MagicMock()
        mock_service.validate.side_effect = [
            {"decision": "enrich", "reason": "unit missing", "building_type": "multi_unit", "suggested_unit_number": None},
            {"decision": "accept", "reason": "structure complete", "building_type": "single_unit", "suggested_unit_number": None},
        ]
        mock_service_cls.return_value = mock_service

        request = CleaningRequest(
            workspace_name="default",
            source_name="third_party",
            opportunity_limit=2,
            preview_limit=50,
        )
        result = asyncio.run(preview_top_review_opportunities(request))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["opportunity_limit"], 2)
        self.assertEqual(result["sampled_rows"], 2)
        self.assertEqual(result["decision_counts"], {"enrich": 1, "accept": 1})
        self.assertEqual(result["projected_recovery_count"], 2)
        self.assertEqual(len(result["selected_batches"]), 2)
        self.assertEqual(result["selected_batches"][0]["batch_id"], "batch-a")

        leaderboard_sql = mock_fetch_all.call_args_list[0].args[0]
        preview_sql = mock_fetch_all.call_args_list[1].args[0]
        self.assertIn("HAVING review_count > 0", leaderboard_sql)
        self.assertIn('acr.decision = "review"', preview_sql)
        self.assertIn('JSON_UNQUOTE(JSON_EXTRACT(rar.source_payload, "$.batch_id")) = %s', preview_sql)


if __name__ == "__main__":
    unittest.main()
