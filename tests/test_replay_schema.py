from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from addressforge.pipelines.schema import _ensure_historical_replay_tables


class TestReplaySchema(unittest.TestCase):
    @patch("addressforge.pipelines.schema._index_exists", return_value=False)
    @patch("addressforge.pipelines.schema._column_exists", return_value=False)
    @patch("addressforge.pipelines.schema.db_cursor")
    def test_forward_migration_adds_replay_evidence_columns_and_index(
        self,
        mock_db_cursor,
        _mock_column_exists,
        _mock_index_exists,
    ) -> None:
        connection = MagicMock()
        cursor = MagicMock()
        mock_db_cursor.return_value.__enter__.return_value = (connection, cursor)

        _ensure_historical_replay_tables()

        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertTrue(
            any("candidate_runtime_identity_json" in sql for sql in statements)
        )
        self.assertTrue(any("processing_status" in sql for sql in statements))
        self.assertTrue(
            any("idx_historical_replay_result_status" in sql for sql in statements)
        )
        connection.commit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
