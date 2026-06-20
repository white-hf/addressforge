from __future__ import annotations

import unittest
import json
from unittest.mock import MagicMock, patch
from addressforge.core.common import fetch_all, db_cursor
from addressforge.services.fusion_service import run_reference_fusion, run_unit_mining, run_reference_enrichment_pipeline

class TestReferenceFusionService(unittest.TestCase):
    def setUp(self):
        self.workspace = "test_fusion_ws"
        # Ensure clean state in test database
        with db_cursor() as (conn, cursor):
            cursor.execute("DELETE FROM canonical_unit WHERE workspace_name = %s", (self.workspace,))
            cursor.execute("DELETE FROM canonical_building WHERE workspace_name = %s", (self.workspace,))
            cursor.execute("DELETE FROM external_building_reference WHERE workspace_name = %s", (self.workspace,))
            cursor.execute("DELETE FROM address_cleaning_result WHERE workspace_name = %s", (self.workspace,))
            conn.commit()

    def tearDown(self):
        with db_cursor() as (conn, cursor):
            cursor.execute("DELETE FROM canonical_unit WHERE workspace_name = %s", (self.workspace,))
            cursor.execute("DELETE FROM canonical_building WHERE workspace_name = %s", (self.workspace,))
            cursor.execute("DELETE FROM external_building_reference WHERE workspace_name = %s", (self.workspace,))
            cursor.execute("DELETE FROM address_cleaning_result WHERE workspace_name = %s", (self.workspace,))
            conn.commit()

    def test_reference_fusion_deduplicates_and_groups(self):
        # Insert duplicate building references:
        # Two references pointing to the same building "100 Albro Lake Rd, Halifax, NS"
        # One from geonova, one from osm
        with db_cursor() as (conn, cursor):
            cursor.execute(
                """
                INSERT INTO external_building_reference (
                    workspace_name, source_name, external_id, street_number, street_name,
                    city, province, reference_tier, quality_score, is_active
                ) VALUES 
                (%s, 'geonova', 'geo-100', '100', 'Albro Lake Rd', 'Halifax', 'NS', 'authoritative', 0.95, 1),
                (%s, 'osm', 'osm-100', '100', 'Albro Lake Rd', 'Halifax', 'NS', 'semi_authoritative', 0.85, 1)
                """,
                (self.workspace, self.workspace)
            )
            conn.commit()

        # Run reference fusion
        result = run_reference_fusion(self.workspace)
        self.assertEqual(result["buildings_fused"], 1)
        self.assertEqual(result["total_references_processed"], 2)

        # Check canonical_building contains the fused building
        buildings = fetch_all("SELECT * FROM canonical_building WHERE workspace_name = %s", (self.workspace,))
        self.assertEqual(len(buildings), 1)
        b = buildings[0]
        self.assertEqual(b["street_number"], "100")
        self.assertEqual(b["street_name"], "Albro Lake Rd")
        self.assertEqual(b["city"], "Halifax")

        # Source attribution should list both geonova and osm source refs
        attrib = json.loads(b["source_attribution"]) if isinstance(b["source_attribution"], str) else b["source_attribution"]
        self.assertEqual(len(attrib), 2)
        source_names = {x["source_name"] for x in attrib}
        self.assertIn("geonova", source_names)
        self.assertIn("osm", source_names)

    def test_unit_mining_backfills_canonical_units(self):
        # 1. Create a building in canonical_building first (so unit inserts don't fail constraint)
        # Using geonova-123's hashed key
        import hashlib
        b_key = hashlib.sha256(b"REF|CA|geo-123").hexdigest()
        with db_cursor() as (conn, cursor):
            cursor.execute(
                """
                INSERT INTO canonical_building (
                    workspace_name, building_key, street_number, street_name, city, province, is_active
                ) VALUES (%s, %s, '123', 'Main St', 'Halifax', 'NS', 1)
                """,
                (self.workspace, b_key)
            )
            # 2. Insert high-confidence cleaning result with unit 4A
            cursor.execute(
                """
                INSERT INTO address_cleaning_result (
                    workspace_name, raw_id, raw_address_text, decision, confidence, suggested_unit_number, reference_json, checkpoint_status
                ) VALUES (%s, 1001, '4A-123 Main St', 'accept', 0.95, '4A', '{"external_id": "geo-123"}', 'completed')
                """,
                (self.workspace,)
            )
            conn.commit()

        # Run unit mining
        result = run_unit_mining(self.workspace)
        self.assertEqual(result["units_mined"], 1)

        # Verify unit 4A exists in canonical_unit
        units = fetch_all("SELECT * FROM canonical_unit WHERE workspace_name = %s", (self.workspace,))
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["unit_number"], "4A")
        self.assertEqual(units[0]["building_key"], b_key)

        # Run again to ensure deduplication/updates do not fail or recount
        result_re = run_unit_mining(self.workspace)
        self.assertEqual(result_re["units_mined"], 0)

if __name__ == "__main__":
    unittest.main()
