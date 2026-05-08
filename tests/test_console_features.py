import unittest
from unittest.mock import patch, MagicMock
import json
import time
from datetime import datetime, timedelta

# Temporarily add src to path for testing
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from addressforge.core.common import db_cursor, fetch_all
from addressforge.control.jobs import count_cleaning_results, set_setting
from addressforge.console.server import app as console_app
from fastapi.testclient import TestClient

class TestConsoleFeatures(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(console_app)
        # Ensure a clean state
        with db_cursor() as (conn, cursor):
            cursor.execute("DELETE FROM address_cleaning_result WHERE workspace_name = 'test_console'")
            cursor.execute("DELETE FROM control_setting WHERE workspace_name = 'test_console'")
            conn.commit()

    def tearDown(self):
        with db_cursor() as (conn, cursor):
            cursor.execute("DELETE FROM address_cleaning_result WHERE workspace_name = 'test_console'")
            cursor.execute("DELETE FROM control_setting WHERE workspace_name = 'test_console'")
            conn.commit()

    def test_count_cleaning_results(self):
        """
        Tests if cleaning results are counted correctly by decision.
        测试清洗结果是否能按决策正确计数。
        """
        with db_cursor() as (conn, cursor):
            # Insert mock data
            # 插入模拟数据
            sql = """
                INSERT INTO address_cleaning_result 
                (workspace_name, raw_id, raw_address_text, decision) 
                VALUES (%s, %s, %s, %s)
            """
            records = [
                ('test_console', 101, '123 Main St', 'accept'),
                ('test_console', 102, '456 Oak Ave', 'accept'),
                ('test_console', 103, '789 Pine Ln', 'review'),
                ('test_console', 104, '101 Maple Dr', 'pending'),
            ]
            cursor.executemany(sql, records)
            conn.commit()

        # Assert counts
        # 断言计数
        accepted_count = count_cleaning_results('test_console', decision='accept')
        review_count = count_cleaning_results('test_console', decision='review')
        total_count = count_cleaning_results('test_console')

        self.assertEqual(accepted_count, 2)
        self.assertEqual(review_count, 1)
        self.assertEqual(total_count, 4)

    def test_worker_liveness_check(self):
        """
        Tests the worker heartbeat detection logic.
        测试 worker 心跳检测逻辑。
        """
        # 1. Simulate recent heartbeat
        # 1. 模拟最近的心跳
        now = datetime.now()
        set_setting("test_console", "worker.global.last_seen", now.strftime("%Y-%m-%d %H:%M:%S"))

        # 2. Check API - should be active
        # 2. 检查 API - 应该是在线状态
        response = self.client.get("/api/v1/control/status?workspace_name=test_console")
        self.assertTrue(response.json()["is_worker_active"])

        # 3. Simulate ancient heartbeat
        # 3. 模拟一个很早的心跳
        ancient_time = now - timedelta(seconds=60)
        set_setting("test_console", "worker.global.last_seen", ancient_time.strftime("%Y-%m-%d %H:%M:%S"))

        # 4. Check API again - should be inactive
        # 4. 再次检查 API - 应该是离线状态
        response = self.client.get("/api/v1/control/status?workspace_name=test_console")
        self.assertFalse(response.json()["is_worker_active"])

    @patch('addressforge.console.server.subprocess.Popen')
    def test_start_worker_api(self, mock_popen):
        """
        Tests that the start worker API attempts to call the correct script.
        测试启动 worker 的 API 是否尝试调用了正确的脚本。
        """
        # Mock the Popen call to avoid actually running a subprocess
        # 模拟 Popen 调用以避免实际运行子进程
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        response = self.client.post("/api/v1/control/worker/start")
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "starting", "pid": 12345})

        # Verify that Popen was called with the path to our script
        # 验证 Popen 是否使用了我们的脚本路径进行调用
        self.assertTrue(mock_popen.called)
        call_args = mock_popen.call_args[0][0]
        self.assertIn('run_control_worker.sh', call_args[0])

    def test_ingestion_config_round_trip(self):
        payload = {
            "workspace_name": "test_console",
            "mode": "db",
            "source_name": "historical_db_backfill",
            "api": {"batch_size": 1500},
            "db": {
                "batch_size": 2000,
                "table": "address_raw_history",
                "cursor_column": "created_at",
                "tiebreaker_column": "order_id",
                "external_id_column": "order_id",
                "raw_address_column": "raw_address_text",
                "postal_code_column": "zipcode",
                "latitude_column": "gps_lat",
                "longitude_column": "gps_lon",
                "city_column": "",
                "province_column": "",
            },
        }

        response = self.client.post("/api/v1/control/ingestion-config", json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "updated")
        self.assertEqual(body["ingestion_config"]["mode"], "db")
        self.assertEqual(body["ingestion_config"]["source_name"], "historical_db_backfill")
        self.assertEqual(body["ingestion_config"]["db"]["table"], "address_raw_history")
        self.assertEqual(body["ingestion_config"]["db"]["tiebreaker_column"], "order_id")

        status = self.client.get("/api/v1/control/status?workspace_name=test_console")
        self.assertEqual(status.status_code, 200)
        status_body = status.json()
        self.assertEqual(status_body["ingestion_config"]["mode"], "db")
        self.assertEqual(status_body["ingestion_config"]["db"]["cursor_column"], "created_at")
        self.assertEqual(status_body["ingestion_config"]["db"]["external_id_column"], "order_id")
        self.assertEqual(status_body["ingestion_config"]["db"]["city_column"], "")
        self.assertEqual(status_body["ingestion_config"]["db"]["province_column"], "")


class TestConsoleJobListLogic(unittest.TestCase):
    @patch("addressforge.control.jobs.db_cursor")
    @patch("addressforge.control.jobs._active_worker_names")
    @patch("addressforge.control.jobs.fetch_all")
    def test_reconcile_stale_running_jobs_marks_zombie_rows_failed(self, mock_fetch_all, mock_active_workers, mock_db_cursor):
        """
        Tests that stale running jobs claimed by dead workers are reconciled to failed.
        测试由失活 worker 持有的僵尸 running 任务会被回收为 failed。
        """
        from addressforge.control.jobs import reconcile_stale_running_jobs

        started_at = (datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        mock_active_workers.return_value = set()
        mock_fetch_all.side_effect = [
            [
                {
                    "job_id": 101,
                    "claimed_by": "worker-dead",
                    "started_at": started_at,
                    "updated_at": started_at,
                }
            ],
            [
                {
                    "job_id": 101,
                    "claimed_by": "worker-dead",
                    "status": "running",
                    "started_at": started_at,
                    "updated_at": started_at,
                    "finished_at": None,
                }
            ],
        ]

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db_cursor.return_value.__enter__.return_value = (mock_conn, mock_cursor)

        reconciled = reconcile_stale_running_jobs("test_console", stale_after_seconds=30)

        self.assertEqual(reconciled, [101])
        mock_cursor.execute.assert_called()
        executed_sql = mock_cursor.execute.call_args[0][0]
        self.assertIn("UPDATE control_job", executed_sql)
        mock_conn.commit.assert_called_once()

    @patch("addressforge.control.jobs.reconcile_stale_running_jobs")
    @patch("addressforge.control.jobs._active_worker_names")
    @patch("addressforge.control.jobs.fetch_all")
    def test_list_jobs_prioritizes_live_running_then_queued_then_recent(self, mock_fetch_all, mock_active_workers, mock_reconcile):
        """
        Tests that the jobs list prioritizes true running jobs, then queued jobs, then recent completed jobs.
        测试任务列表会优先真实 running，其次 queued，之后再按最近时间显示其他任务。
        """
        from addressforge.control.jobs import list_jobs

        mock_reconcile.return_value = []
        mock_active_workers.return_value = {"worker-live"}
        mock_fetch_all.return_value = [
            {
                "job_id": 1,
                "workspace_name": "test_console",
                "job_kind": "cleaning_once",
                "status": "succeeded",
                "claimed_by": "worker-old",
                "created_at": "2026-05-07 11:00:00",
                "started_at": "2026-05-07 11:00:01",
                "updated_at": "2026-05-07 11:00:03",
            },
            {
                "job_id": 2,
                "workspace_name": "test_console",
                "job_kind": "cleaning_once",
                "status": "queued",
                "claimed_by": None,
                "created_at": "2026-05-07 11:10:00",
                "started_at": None,
                "updated_at": "2026-05-07 11:10:00",
            },
            {
                "job_id": 3,
                "workspace_name": "test_console",
                "job_kind": "cleaning_once",
                "status": "running",
                "claimed_by": "worker-live",
                "created_at": "2026-05-07 11:05:00",
                "started_at": "2026-05-07 11:05:01",
                "updated_at": "2026-05-07 11:05:02",
            },
            {
                "job_id": 4,
                "workspace_name": "test_console",
                "job_kind": "cleaning_once",
                "status": "failed",
                "claimed_by": "worker-old",
                "created_at": "2026-05-07 11:20:00",
                "started_at": "2026-05-07 11:20:00",
                "updated_at": "2026-05-07 11:20:05",
            },
        ]

        rows = list_jobs("test_console", limit=10)

        self.assertEqual([row["job_id"] for row in rows[:4]], [3, 2, 4, 1])
        self.assertEqual(rows[0]["display_status"], "running")
        self.assertEqual(rows[1]["display_status"], "queued")

    @patch("addressforge.control.jobs.reconcile_stale_running_jobs")
    @patch("addressforge.control.jobs.fetch_all")
    def test_summarize_latest_ingestion_cleaning_batch(self, mock_fetch_all, mock_reconcile):
        """
        Tests that latest batch summary aggregates imported and cleaned counts from related jobs.
        测试最新批次摘要会自动汇总导入和清洗数量。
        """
        from addressforge.control.jobs import summarize_latest_ingestion_cleaning_batch

        mock_reconcile.return_value = []
        mock_fetch_all.side_effect = [
            [
                {
                    "job_id": 200,
                    "workspace_name": "test_console",
                    "job_kind": "ingestion_once",
                    "status": "succeeded",
                    "created_at": "2026-05-07 11:00:00",
                    "finished_at": "2026-05-07 11:00:05",
                    "result_json": json.dumps({"result": {"records_ingested": 2488}}),
                },
                {
                    "job_id": 199,
                    "workspace_name": "test_console",
                    "job_kind": "ingestion_once",
                    "status": "succeeded",
                    "created_at": "2026-05-07 10:00:00",
                    "finished_at": "2026-05-07 10:00:05",
                    "result_json": json.dumps({"result": {"records_ingested": 1000}}),
                },
            ],
            [
                {
                    "job_id": 201,
                    "workspace_name": "test_console",
                    "job_kind": "cleaning_once",
                    "status": "failed",
                    "created_at": "2026-05-07 11:00:06",
                    "finished_at": "2026-05-07 11:01:00",
                },
                {
                    "job_id": 202,
                    "workspace_name": "test_console",
                    "job_kind": "cleaning_once",
                    "status": "succeeded",
                    "created_at": "2026-05-07 11:01:00",
                    "finished_at": "2026-05-07 11:02:00",
                    "result_json": json.dumps({"result": {"records_processed": 1000}}),
                },
                {
                    "job_id": 203,
                    "workspace_name": "test_console",
                    "job_kind": "cleaning_once",
                    "status": "succeeded",
                    "created_at": "2026-05-07 11:02:01",
                    "finished_at": "2026-05-07 11:03:00",
                    "result_json": json.dumps({"result": {"records_processed": 559}}),
                },
            ],
        ]

        summary = summarize_latest_ingestion_cleaning_batch("test_console")

        self.assertTrue(summary["has_batch"])
        self.assertEqual(summary["latest_ingestion_job_id"], 200)
        self.assertEqual(summary["records_ingested"], 2488)
        self.assertEqual(summary["records_cleaned"], 1559)
        self.assertEqual(summary["cleaning_job_count"], 3)
        self.assertEqual(summary["cleaning_succeeded"], 2)
        self.assertEqual(summary["cleaning_failed"], 1)
        self.assertEqual(summary["latest_cleaning_job_id"], 203)

if __name__ == '__main__':
    unittest.main()
