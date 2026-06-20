from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from addressforge.ingestion.providers import DatabaseIngestionProvider
from addressforge.ingestion.providers import ApiIngestionProvider


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


class TestApiIngestionProvider(unittest.TestCase):
    def test_api_provider_forwards_batch_list_override_from_runtime_config(self):
        adapter = MagicMock()
        adapter.fetch_page.return_value = MagicMock()

        with patch("addressforge.ingestion.providers.resolve_api_source_adapter", return_value=adapter):
            provider = ApiIngestionProvider(
                api_url="https://example.com",
                token="token",
                timeout=10,
                source_name="third_party",
                batch_list_override="HASUB-202605150116",
            )
            provider.fetch_page(cursor_value=None, batch_size=100)

        self.assertEqual(adapter.fetch_page.call_count, 1)
        context = adapter.fetch_page.call_args.args[1]
        self.assertEqual(context.batch_list_override, "HASUB-202605150116")
        self.assertEqual(context.source_name, "third_party")


if __name__ == "__main__":
    unittest.main()
