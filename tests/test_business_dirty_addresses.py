import json
import unittest
from unittest.mock import patch

from addressforge.services.business_service import list_dirty_address_diagnostics


class DirtyAddressDiagnosticsTests(unittest.TestCase):
    @patch("addressforge.services.business_service.fetch_all")
    def test_lists_dirty_rows_with_batch_filter_and_suggestions(self, mock_fetch_all):
        mock_fetch_all.return_value = [
            {
                "raw_id": 101,
                "raw_address_text": "50 Bedford Hwy halifax nova scotia,307,Halifax,Nova Scotia,Canada,B3M 0J9",
                "decision": "enrich",
                "confidence": 0.91,
                "reason": "Reference matched a multi-unit building; unit may be missing.",
                "building_type": "multi_unit",
                "suggested_unit_number": None,
                "validation_json": json.dumps(
                    {
                        "decision": "enrich",
                        "reason": "Reference matched a multi-unit building; unit may be missing.",
                        "confidence": 0.91,
                        "canonical": {
                            "street_number": "50",
                            "street_name": "BEDFORD HWY",
                            "city": "Halifax",
                            "province": "NS",
                            "postal_code": "B3M 0J9",
                        },
                        "hints": {
                            "gps_conflict": True,
                            "reference_score": 0.41,
                            "reference_gap_reason": "reference_candidate_found_but_matcher_threshold",
                            "parser_disagreement": False,
                        },
                    }
                ),
                "reference_json": json.dumps(
                    {
                        "external_id": "REF-1",
                        "reference_unit_numbers": ["307", "308"],
                    }
                ),
                "parser_json": json.dumps(
                    {
                        "best_candidate": {
                            "parsed": {
                                "street_number": "50",
                                "street_name": "BEDFORD HWY",
                                "city": "Halifax",
                                "province": "NS",
                            }
                        }
                    }
                ),
                "source_name": "third_party",
                "city": "Halifax",
                "province": "NS",
                "postal_code": "B3M 0J9",
                "country_code": "CA",
                "latitude": None,
                "longitude": None,
                "source_payload": json.dumps({"batch_id": "BATCH-7"}),
                "batch_id": "BATCH-7",
                "updated_at": "2026-05-14 10:00:00",
            }
        ]

        result = list_dirty_address_diagnostics(
            "default",
            source_name="third_party",
            batch_id="BATCH-7",
            limit=20,
        )

        self.assertEqual(result["counts"]["total"], 1)
        item = result["items"][0]
        self.assertEqual(item["batch_id"], "BATCH-7")
        self.assertIn("missing_unit", item["categories"])
        self.assertIn("gps_conflict", item["categories"])
        self.assertIn("reference_gap", item["categories"])
        self.assertEqual(item["suggested_unit_number"], "307")
        self.assertEqual(item["suggested_address"]["street_number"], "50")
        self.assertEqual(item["suggested_address"]["street_name"], "BEDFORD HWY")
        self.assertEqual(item["suggested_address"]["unit_number"], "307")
        query, params = mock_fetch_all.call_args.args
        self.assertIn("JSON_UNQUOTE(JSON_EXTRACT(r.source_payload, '$.batch_id')) = %s", query)
        self.assertEqual(params[2], "third_party")
        self.assertEqual(params[3], "BATCH-7")

    @patch("addressforge.services.business_service.fetch_all")
    def test_skips_rows_without_target_dirty_categories(self, mock_fetch_all):
        mock_fetch_all.return_value = [
            {
                "raw_id": 102,
                "raw_address_text": "14 Park Street, Trenton, NS",
                "decision": "accept",
                "confidence": 0.95,
                "reason": "Reference matched a single-unit building.",
                "building_type": "single_unit",
                "suggested_unit_number": None,
                "validation_json": json.dumps(
                    {
                        "decision": "accept",
                        "reason": "Reference matched a single-unit building.",
                        "confidence": 0.95,
                        "canonical": {"street_number": "14", "street_name": "PARK STREET"},
                        "hints": {"gps_conflict": False, "parser_disagreement": False},
                    }
                ),
                "reference_json": json.dumps({"external_id": "REF-2"}),
                "parser_json": "{}",
                "source_name": "third_party",
                "city": "Trenton",
                "province": "NS",
                "postal_code": None,
                "country_code": "CA",
                "latitude": None,
                "longitude": None,
                "source_payload": "{}",
                "batch_id": None,
                "updated_at": "2026-05-14 11:00:00",
            }
        ]

        result = list_dirty_address_diagnostics("default", limit=10)
        self.assertEqual(result["counts"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
