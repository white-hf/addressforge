import unittest
from unittest.mock import MagicMock, patch

from addressforge.core.common import create_run


class TestCommonRunTypes(unittest.TestCase):
    @patch("addressforge.core.common.db_cursor")
    def test_create_run_maps_residual_active_learning_to_supported_enum(self, mock_db_cursor):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 123
        mock_db_cursor.return_value.__enter__.return_value = (mock_conn, mock_cursor)
        mock_db_cursor.return_value.__exit__.return_value = False

        run_id = create_run("ml_active_learning_residual", notes="scope=test/batch")

        self.assertEqual(run_id, 123)
        mock_cursor.execute.assert_called_once()
        sql, params = mock_cursor.execute.call_args[0]
        self.assertIn("INSERT INTO etl_run", sql)
        self.assertEqual(params[0], "ml_active_learning")
        self.assertEqual(params[1], "scope=test/batch")
        mock_conn.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
