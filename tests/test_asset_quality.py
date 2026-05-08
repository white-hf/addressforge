import unittest
from unittest.mock import patch

from addressforge.services.asset_service import (
    _classify_promotion_row,
    _classify_hotspot_risk,
    _classify_unit_convergence_quality,
    _derive_asset_quality_diagnostics,
    _derive_reference_gap_diagnostics,
    _extract_structured_fields,
    _plan_canonical_unit_variant_merge,
    _normalize_canonical_unit_value,
    _recover_locality_from_raw_text,
    _resolve_canonical_building_payload,
    promote_results_to_assets,
)


class AssetQualityTests(unittest.TestCase):
    def test_recover_locality_from_raw_text_handles_common_canada_tails(self):
        city, province = _recover_locality_from_raw_text("15-333 Windmill Rd Dartmouth NS")
        self.assertEqual(city, "Dartmouth")
        self.assertEqual(province, "NS")

        city2, province2 = _recover_locality_from_raw_text("60 CORNWALIAS, LUNENBERG, NS")
        self.assertEqual(city2, "Lunenberg")
        self.assertEqual(province2, "NS")

        city3, province3 = _recover_locality_from_raw_text("28 Sunnydale Ave DARTMOUTH")
        self.assertEqual(city3, "Dartmouth")
        self.assertIsNone(province3)

        city4, province4 = _recover_locality_from_raw_text("2173 Hwy1 West Rd Apt3 Auburn Nova Scotia")
        self.assertEqual(city4, "Auburn")
        self.assertEqual(province4, "NS")

    def test_asset_quality_diagnostics_distinguish_reference_and_unit_gaps(self):
        rows = [
            {
                "raw_id": 1,
                "raw_address_text": "1122 Tower Road, 312 Halifax NS",
                "street_number": "1122",
                "street_name": "TOWER ROAD",
                "base_address_key": "BASE1",
                "suggested_unit_number": "312",
                "building_type": "multi_unit",
                "reference_json": '{"external_id":"REF-1"}',
                "country_code": "CA",
                "confidence": 0.95,
                "city": "HALIFAX",
                "province": "NS",
            },
            {
                "raw_id": 2,
                "raw_address_text": "1122 Tower Road, 314 Halifax NS",
                "street_number": "1122",
                "street_name": "TOWER ROAD",
                "base_address_key": "BASE1",
                "suggested_unit_number": "314",
                "building_type": "multi_unit",
                "reference_json": '{"external_id":"REF-1"}',
                "country_code": "CA",
                "confidence": 0.96,
                "city": "HALIFAX",
                "province": "NS",
            },
            {
                "raw_id": 3,
                "raw_address_text": "14 Park Street, Trenton, NS",
                "street_number": "14",
                "street_name": "PARK STREET",
                "base_address_key": "BASE2",
                "suggested_unit_number": None,
                "building_type": "single_unit",
                "reference_json": "{}",
                "country_code": "CA",
                "confidence": 0.91,
                "city": "TRENTON",
                "province": "NS",
            },
            {
                "raw_id": 4,
                "raw_address_text": "128 Highbury Rd Apt 2 New Minas NS",
                "street_number": "128",
                "street_name": "HIGHBURY RD",
                "base_address_key": "BASE3",
                "suggested_unit_number": None,
                "building_type": "multi_unit",
                "reference_json": "{}",
                "country_code": "CA",
                "confidence": 0.9,
                "city": "NEW MINAS",
                "province": "NS",
            },
            {
                "raw_id": 5,
                "raw_address_text": "500 Unknown Rd, NS",
                "street_number": "500",
                "street_name": "UNKNOWN RD",
                "base_address_key": "BASE4",
                "suggested_unit_number": None,
                "building_type": "single_unit",
                "reference_json": "{}",
                "country_code": "CA",
                "confidence": 0.88,
                "city": None,
                "province": "NS",
            },
        ]
        diagnostics = _derive_asset_quality_diagnostics(
            rows,
            canonical_building_count=2,
            canonical_unit_count=1,
            confidence_threshold=0.85,
        )
        self.assertEqual(diagnostics["eligible_rows"], 5)
        self.assertEqual(diagnostics["eligible_reference_rows"], 2)
        self.assertEqual(diagnostics["eligible_non_reference_rows"], 2)
        self.assertEqual(diagnostics["eligible_multi_unit_rows"], 3)
        self.assertEqual(diagnostics["eligible_multi_unit_without_unit_rows"], 1)
        self.assertEqual(diagnostics["unique_building_keys_total"], 3)
        self.assertEqual(diagnostics["unique_reference_backed_building_keys"], 1)
        self.assertEqual(diagnostics["unique_unit_keys_total"], 2)
        self.assertEqual(diagnostics["promotion_skip_reason_counts"]["missing_city"], 1)
        self.assertGreater(len(diagnostics["multi_unit_without_unit_examples"]), 0)
        self.assertGreater(len(diagnostics["duplicate_building_key_hotspots"]), 0)
        self.assertIn("reference_backed_building_hotspots", diagnostics)
        self.assertIn("non_reference_building_hotspots", diagnostics)
        self.assertIn("unit_convergence_hotspots", diagnostics)
        self.assertIn("hotspot_risk_summary", diagnostics)

    def test_plan_canonical_unit_variant_merge_merges_dirty_variants(self):
        normalized_key = "unit-key-clean"
        plan = _plan_canonical_unit_variant_merge(
            [
                {
                    "unit_key": normalized_key,
                    "unit_number": "2904",
                    "source_attribution": "[\"1\"]",
                },
                {
                    "unit_key": "unit-key-dirty-1",
                    "unit_number": "NUMBER 2904",
                    "source_attribution": "[\"2\"]",
                },
                {
                    "unit_key": "unit-key-dirty-2",
                    "unit_number": "2904 UNIT NUMBER",
                    "source_attribution": "[\"3\"]",
                },
            ],
            normalized_unit="2904",
            normalized_key=normalized_key,
        )
        self.assertTrue(plan["has_matching_variants"])
        self.assertEqual(plan["target_row"]["unit_key"], normalized_key)
        self.assertEqual(
            sorted(plan["duplicate_keys"]),
            ["unit-key-dirty-1", "unit-key-dirty-2"],
        )
        self.assertEqual(plan["merged_source_attribution"], "[\"1\", \"2\", \"3\"]")

    def test_classify_hotspot_risk_downgrades_homogeneous_single_unit_repeats(self):
        self.assertEqual(
            _classify_hotspot_risk(
                raw_id_count=6,
                unit_key_count=0,
                reference_backed=False,
                homogeneous_repeat=True,
                single_unit_only=True,
            ),
            "low_risk_repeat",
        )

    def test_classify_unit_convergence_quality_treats_single_unit_with_strong_unit_hint_as_benign(self):
        quality, counts = _classify_unit_convergence_quality(
            [
                {
                    "raw_address_text": "5681 Rhuland St Unit 302 Halifax NS",
                    "street_name": "RHULAND ST",
                    "building_type": "multi_unit",
                    "suggested_unit_number": "302",
                },
                {
                    "raw_address_text": "5681 Rhuland St #9 Halifax NS",
                    "street_name": "RHULAND ST #9",
                    "building_type": "single_unit",
                    "suggested_unit_number": None,
                },
            ]
        )
        self.assertEqual(quality, "benign_multi_unit_convergence")
        self.assertEqual(counts["single_unit_rows"], 1)
        self.assertEqual(counts["single_unit_rows_with_unit_hint"], 1)

    def test_classify_unit_convergence_quality_treats_small_label_noise_inside_multi_unit_cluster_as_benign(self):
        quality, counts = _classify_unit_convergence_quality(
            [
                {
                    "raw_address_text": "5870 Demone St Suite 1801 Halifax NS",
                    "street_name": "DEMONE ST",
                    "building_type": "commercial",
                    "suggested_unit_number": "1801",
                },
                {
                    "raw_address_text": "5870 Demone Street, 602, HALIFAX, NS",
                    "street_name": "DEMONE ST",
                    "building_type": "single_unit",
                    "suggested_unit_number": "602",
                },
                {
                    "raw_address_text": "5870 Demone St 403 Halifax NS",
                    "street_name": "DEMONE ST",
                    "building_type": "multi_unit",
                    "suggested_unit_number": "403",
                },
                {
                    "raw_address_text": "5870 Demone St 504 Halifax NS",
                    "street_name": "DEMONE ST",
                    "building_type": "multi_unit",
                    "suggested_unit_number": "504",
                },
                {
                    "raw_address_text": "5870 Demone St 803 Halifax NS",
                    "street_name": "DEMONE ST",
                    "building_type": "multi_unit",
                    "suggested_unit_number": "803",
                },
            ]
        )
        self.assertEqual(quality, "benign_multi_unit_convergence")
        self.assertEqual(counts["single_unit_rows"], 1)
        self.assertEqual(counts["commercial_rows"], 1)

    def test_extract_structured_fields_strips_unit_tail_from_street_name(self):
        structured = _extract_structured_fields(
            {
                "raw_address_text": "7001 MUMFORD ROAD STE 124, HALIFAX, NS, B3L4R3, CA",
                "street_number": "7001",
                "street_name": "MUMFORD ROAD STE 124",
                "suggested_unit_number": "124",
                "normalize_json": "{}",
                "reference_json": "{}",
                "parser_json": "{}",
            }
        )
        self.assertEqual(structured["street_name"], "MUMFORD ROAD")

    @patch("addressforge.services.asset_service.fetch_all")
    def test_reference_gap_diagnostics_treat_road_and_rd_as_equivalent(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "external_id": "319817327",
                "street_number": "7001",
                "street_name": "MUMFORD RD",
                "unit_number": None,
                "city": "Halifax",
                "municipality": "Hrm",
                "county": "Halifax County",
                "province": "NS",
                "quality_score": 0.95,
                "reference_tier": "authoritative",
            }
        ]
        diagnostics = _derive_reference_gap_diagnostics(
            "default",
            [
                {
                    "building_key": "bk",
                    "hotspot_risk": "likely_reference_gap",
                    "row_details": [
                        {
                            "raw_id": 11055,
                            "raw_address_text": "7001 MUMFORD ROAD STE 124, HALIFAX, NS, B3L4R3, CA",
                            "street_number": "7001",
                            "street_name": "MUMFORD ROAD",
                            "city": "Halifax",
                            "province": "NS",
                            "raw_tail_city": "Halifax",
                            "raw_tail_province": "NS",
                        }
                    ],
                }
            ],
        )
        self.assertEqual(
            diagnostics["reference_gap_reason_summary"]["reference_candidate_found_but_matcher_threshold"],
            1,
        )

    @patch("addressforge.services.asset_service.fetch_all")
    def test_attach_hotspot_details_returns_row_level_examples(self, mock_fetch):
        from addressforge.services.asset_service import _attach_hotspot_details

        mock_fetch.return_value = [
            {
                "raw_id": 10,
                "raw_address_text": "12 Main St Unit 2 Halifax NS",
                "building_type": "multi_unit",
                "suggested_unit_number": "2",
                "confidence": 0.95,
                "base_address_key": "KEY1",
                "normalize_json": '{"normalized_city":"Halifax","normalized_province":"NS"}',
                "reference_json": "{}",
                "parser_json": '{"best_candidate":{"parsed":{"street_number":"12","street_name":"MAIN ST"}}}',
                "country_code": "CA",
            }
        ]
        hotspots = [{"building_key": "abc", "raw_ids": [10]}]
        detailed = _attach_hotspot_details("default", hotspots, limit=5)
        self.assertEqual(len(detailed), 1)
        self.assertIn("row_details", detailed[0])
        self.assertEqual(detailed[0]["row_details"][0]["street_name"], "MAIN ST")
        self.assertEqual(detailed[0]["row_details"][0]["raw_tail_city"], "Halifax")

    @patch("addressforge.services.asset_service.fetch_all")
    def test_reference_gap_diagnostics_distinguish_locality_and_street_tail_mismatch(self, mock_fetch):
        mock_fetch.side_effect = [
            [
                {
                    "external_id": "REF-LOCALITY",
                    "street_number": "4546",
                    "street_name": "PICTOU LANDING RD HILLSIDE",
                    "city": "Hillside",
                    "municipality": None,
                    "county": None,
                    "province": "NS",
                    "unit_number": "1",
                    "quality_score": 0.95,
                    "reference_tier": "authoritative",
                }
            ],
            [
                {
                    "external_id": "REF-TAIL",
                    "street_number": "4546",
                    "street_name": "PICTOU LANDING RD",
                    "city": "Trenton",
                    "municipality": None,
                    "county": None,
                    "province": "NS",
                    "unit_number": "1",
                    "quality_score": 0.95,
                    "reference_tier": "authoritative",
                }
            ],
            [],
        ]
        hotspot_details = [
            {
                "building_key": "BK1",
                "row_details": [
                    {
                        "raw_id": 537,
                        "raw_address_text": "4546 Pictou landing Rd Hillside Apt 4 TRENTON",
                        "street_number": "4546",
                        "street_name": "PICTOU LANDING RD HILLSIDE",
                        "city": "Trenton",
                        "province": "NS",
                    },
                    {
                        "raw_id": 538,
                        "raw_address_text": "4546 Pictou landing Rd Apt 4 TRENTON",
                        "street_number": "4546",
                        "street_name": "PICTOU LANDING RD HILLSIDE",
                        "city": "Hillside",
                        "province": "NS",
                    },
                    {
                        "raw_id": 539,
                        "raw_address_text": "999 Unknown Rd Somewhere NS",
                        "street_number": "999",
                        "street_name": "UNKNOWN RD",
                        "city": "Somewhere",
                        "province": "NS",
                    },
                ],
            }
        ]
        diagnostics = _derive_reference_gap_diagnostics("default", hotspot_details)
        summary = diagnostics["reference_gap_reason_summary"]
        self.assertEqual(summary["reference_candidate_found_but_locality_mismatch"], 1)
        self.assertEqual(summary["reference_candidate_found_but_street_tail_mismatch"], 1)
        self.assertEqual(summary["no_reference_candidate_found"], 1)
        self.assertEqual(diagnostics["reference_gap_hotspot_details"][0]["reference_gap_row_examples"][0]["diagnostic_reason"], "reference_candidate_found_but_locality_mismatch")
        self.assertEqual(
            diagnostics["reference_gap_hotspot_details"][0]["reference_gap_action"],
            "review_locality_normalization_and_city_mapping",
        )

    def test_reference_gap_diagnostics_skip_low_risk_repeat_hotspots(self):
        diagnostics = _derive_reference_gap_diagnostics(
            "default",
            [
                {
                    "building_key": "bk",
                    "hotspot_risk": "low_risk_repeat",
                    "row_details": [
                        {
                            "raw_id": 1,
                            "raw_address_text": "207 Sunnyvale Cres LOWER SACKVILLE NS",
                            "street_number": "207",
                            "street_name": "SUNNYVALE CRES LOWER SACKVILLE NS",
                            "city": "Halifax",
                            "province": "NS",
                        }
                    ],
                }
            ],
        )
        self.assertEqual(diagnostics["reference_gap_hotspot_details"], [])
        self.assertTrue(all(value == 0 for value in diagnostics["reference_gap_reason_summary"].values()))

    @patch("addressforge.services.asset_service.fetch_all")
    def test_classify_promotion_row_uses_reference_fallback_for_street_tail_mismatch(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "external_id": "87300134",
                "street_number": "4546",
                "street_name": "PICTOU LANDING RD",
                "unit_number": "1",
                "city": "Hillside",
                "municipality": "Pictou County",
                "county": "Pictou County",
                "province": "NS",
                "quality_score": 0.95,
                "reference_tier": "authoritative",
            }
        ]
        enriched, skip_reason = _classify_promotion_row(
            {
                "raw_id": 537,
                "raw_address_text": "4546 Pictou landing Rd Hillside Apt 4 TRENTON NS",
                "street_number": "4546",
                "street_name": "PICTOU LANDING RD HILLSIDE",
                "building_type": "multi_unit",
                "suggested_unit_number": "4",
                "base_address_key": "BASE-4546",
                "reference_json": "{}",
                "country_code": "CA",
                "city": "Halifax",
                "province": "NS",
            },
            workspace_name="default",
        )
        self.assertIsNone(skip_reason)
        self.assertTrue(enriched["reference_backed"])
        self.assertEqual(enriched["resolved_reference_external_id"], "87300134")
        self.assertNotEqual(enriched["building_key"], "BASE-4546")
        payload = _resolve_canonical_building_payload(enriched)
        self.assertEqual(payload["street_name"], "PICTOU LANDING RD")
        self.assertEqual(payload["city"], "Hillside")

    def test_reference_backed_single_unit_hotspot_is_low_risk_repeat(self):
        self.assertEqual(_classify_hotspot_risk(4, 1, True), "low_risk_repeat")

    def test_unit_convergence_quality_flags_normalization_noise(self):
        quality, counts = _classify_unit_convergence_quality(
            [
                {"building_type": "multi_unit", "suggested_unit_number": "NUMBER 2904"},
                {"building_type": "multi_unit", "suggested_unit_number": "903"},
                {"building_type": "multi_unit", "suggested_unit_number": "413 UNIT NUMBER"},
            ]
        )
        self.assertEqual(quality, "unit_normalization_review")
        self.assertEqual(counts["normalizable_unit_values"], 2)

    def test_normalize_canonical_unit_value_removes_noise_tokens(self):
        self.assertEqual(_normalize_canonical_unit_value("NUMBER 2904"), "2904")
        self.assertEqual(_normalize_canonical_unit_value("413 UNIT NUMBER"), "413")
        self.assertEqual(_normalize_canonical_unit_value("PH 09"), "PH09")

    @patch("addressforge.services.asset_service.fetch_all")
    def test_promote_results_to_assets_returns_observability_fields_for_empty_input(self, mock_fetch):
        mock_fetch.return_value = []
        result = promote_results_to_assets("default")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["promoted_buildings"], 0)
        self.assertEqual(result["promoted_units"], 0)
        self.assertEqual(result["reference_backed_rows_processed"], 0)
        self.assertEqual(result["unique_building_keys_processed"], 0)


if __name__ == "__main__":
    unittest.main()
