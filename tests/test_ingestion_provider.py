from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from addressforge.ingestion.providers import DatabaseIngestionProvider


class TestDatabaseIngestionProvider(unittest.TestCase):
    @patch("addressforge.ingestion.providers.mysql.connector.connect")
    def test_db_provider_uses_composite_cursor_pagination(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        mock_cursor.fetchall.return_value = [
            {
                "order_id": "A100",
                "raw_address_text": "123 Main St",
                "created_at": "2025-10-15 12:38:34",
                "zipcode": "B3K0G9",
                "gps_lat": 44.65,
                "gps_lon": -63.57,
            },
            {
                "order_id": "A101",
                "raw_address_text": "124 Main St",
                "created_at": "2025-10-15 12:38:34",
                "zipcode": "B3K0G9",
                "gps_lat": 44.65,
                "gps_lon": -63.57,
            },
        ]

        provider = DatabaseIngestionProvider(
            host="127.0.0.1",
            user="user",
            password="pw",
            database="db",
            table="address_raw_history",
            cursor_column="created_at",
            tie_breaker_column="order_id",
            source_name="historical_db_backfill",
        )
        page = provider.fetch_page(
            cursor_value=json.dumps({"cursor": "2025-10-15 12:38:34", "tiebreaker": "A099"}),
            batch_size=2,
        )

        executed_sql = mock_cursor.execute.call_args.args[0]
        executed_params = mock_cursor.execute.call_args.args[1]
        self.assertIn("created_at > %s", executed_sql)
        self.assertIn("created_at = %s AND order_id > %s", executed_sql)
        self.assertEqual(executed_params, ("2025-10-15 12:38:34", "2025-10-15 12:38:34", "A099", 2))
        self.assertEqual(page.next_cursor, json.dumps({"cursor": "2025-10-15 12:38:34", "tiebreaker": "A101"}, separators=(",", ":")))
        self.assertEqual(len(page.records), 2)
        self.assertEqual(page.records[0].external_id, "A100")


if __name__ == "__main__":
    unittest.main()
