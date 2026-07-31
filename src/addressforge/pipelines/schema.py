from __future__ import annotations

import os
from pathlib import Path

from addressforge.core.common import db_cursor, ensure_etl_run_types, execute_sql_script, fetch_all
from addressforge.models import bootstrap_default_registry


def _column_exists(table_name: str, column_name: str) -> bool:
    rows = fetch_all(
        """
        SELECT 1 AS ok
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        LIMIT 1
        """,
        (table_name, column_name),
    )
    return bool(rows)


def _index_exists(table_name: str, index_name: str) -> bool:
    rows = fetch_all(
        """
        SELECT 1 AS ok
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND INDEX_NAME = %s
        LIMIT 1
        """,
        (table_name, index_name),
    )
    return bool(rows)


def _ensure_workspace_scoped_tables() -> None:
    with db_cursor() as (conn, cursor):
        if not _column_exists("raw_address_record", "workspace_name"):
            cursor.execute(
                """
                ALTER TABLE raw_address_record
                ADD COLUMN workspace_name VARCHAR(64) NOT NULL DEFAULT 'default' AFTER raw_id
                """
            )
        if _index_exists("raw_address_record", "uq_raw_address_source_external"):
            cursor.execute("ALTER TABLE raw_address_record DROP INDEX uq_raw_address_source_external")
        cursor.execute(
            """
            ALTER TABLE raw_address_record
            ADD UNIQUE KEY uq_raw_address_source_external (workspace_name, source_name, external_id)
            """
        )
        if not _index_exists("raw_address_record", "idx_raw_address_workspace"):
            cursor.execute(
                """
                ALTER TABLE raw_address_record
                ADD KEY idx_raw_address_workspace (workspace_name, source_name)
                """
            )

        if not _column_exists("source_ingestion_cursor", "workspace_name"):
            cursor.execute(
                """
                ALTER TABLE source_ingestion_cursor
                ADD COLUMN workspace_name VARCHAR(64) NOT NULL DEFAULT 'default' AFTER cursor_id
                """
            )
        if _index_exists("source_ingestion_cursor", "uq_source_cursor"):
            cursor.execute("ALTER TABLE source_ingestion_cursor DROP INDEX uq_source_cursor")
        cursor.execute(
            """
            ALTER TABLE source_ingestion_cursor
            ADD UNIQUE KEY uq_source_cursor (workspace_name, source_system, cursor_type)
            """
        )

        if not _column_exists("external_building_reference", "workspace_name"):
            cursor.execute(
                """
                ALTER TABLE external_building_reference
                ADD COLUMN workspace_name VARCHAR(64) NOT NULL DEFAULT 'default' AFTER reference_id
                """
            )
        if _index_exists("external_building_reference", "uq_external_building_reference"):
            cursor.execute("ALTER TABLE external_building_reference DROP INDEX uq_external_building_reference")
        cursor.execute(
            """
            ALTER TABLE external_building_reference
            ADD UNIQUE KEY uq_external_building_reference (workspace_name, source_name, external_id)
            """
        )
        if _index_exists("external_building_reference", "idx_external_building_reference_active"):
            cursor.execute("ALTER TABLE external_building_reference DROP INDEX idx_external_building_reference_active")
        cursor.execute(
            """
            ALTER TABLE external_building_reference
            ADD KEY idx_external_building_reference_active (workspace_name, is_active, source_name)
            """
        )

        if not _column_exists("address_cleaning_result", "normalize_json"):
            cursor.execute(
                """
                ALTER TABLE address_cleaning_result
                ADD COLUMN normalize_json JSON DEFAULT NULL AFTER raw_address_text
                """
            )
        if not _column_exists("address_cleaning_result", "checkpoint_stage"):
            cursor.execute(
                """
                ALTER TABLE address_cleaning_result
                ADD COLUMN checkpoint_stage VARCHAR(32) DEFAULT NULL AFTER reference_json
                """
            )
        if not _column_exists("address_cleaning_result", "checkpoint_status"):
            cursor.execute(
                """
                ALTER TABLE address_cleaning_result
                ADD COLUMN checkpoint_status VARCHAR(24) NOT NULL DEFAULT 'pending' AFTER checkpoint_stage
                """
            )
        if not _column_exists("address_cleaning_result", "checkpoint_error"):
            cursor.execute(
                """
                ALTER TABLE address_cleaning_result
                ADD COLUMN checkpoint_error TEXT DEFAULT NULL AFTER checkpoint_status
                """
            )
        conn.commit()


def _ensure_historical_replay_tables() -> None:
    run_columns = {
        "candidate_model_id": "BIGINT DEFAULT NULL",
        "active_model_id": "BIGINT DEFAULT NULL",
        "requested_count": "INT NOT NULL DEFAULT 0",
        "failure_count": "INT NOT NULL DEFAULT 0",
        "disagreement_count": "INT NOT NULL DEFAULT 0",
        "status": "VARCHAR(24) NOT NULL DEFAULT 'completed'",
        "error_text": "TEXT DEFAULT NULL",
        "candidate_runtime_identity_json": "JSON DEFAULT NULL",
        "active_runtime_identity_json": "JSON DEFAULT NULL",
        "completed_at": "TIMESTAMP NULL DEFAULT NULL",
    }
    result_columns = {
        "candidate_vs_current_different": "BOOLEAN NOT NULL DEFAULT 0",
        "active_vs_current_different": "BOOLEAN NOT NULL DEFAULT 0",
        "processing_status": "VARCHAR(24) NOT NULL DEFAULT 'success'",
        "error_text": "TEXT DEFAULT NULL",
        "current_output_json": "JSON DEFAULT NULL",
        "candidate_output_json": "JSON DEFAULT NULL",
        "active_output_json": "JSON DEFAULT NULL",
    }
    with db_cursor() as (conn, cursor):
        for column_name, definition in run_columns.items():
            if not _column_exists("historical_replay_run", column_name):
                cursor.execute(
                    f"ALTER TABLE historical_replay_run ADD COLUMN {column_name} {definition}"
                )
        for column_name, definition in result_columns.items():
            if not _column_exists("historical_replay_result", column_name):
                cursor.execute(
                    f"ALTER TABLE historical_replay_result ADD COLUMN {column_name} {definition}"
                )
        if not _index_exists(
            "historical_replay_result",
            "idx_historical_replay_result_status",
        ):
            cursor.execute(
                """
                ALTER TABLE historical_replay_result
                ADD KEY idx_historical_replay_result_status (
                    workspace_name, run_id, processing_status
                )
                """
            )
        conn.commit()


def _ensure_review_prescreen_table() -> None:
    # Table is created by schema SQL. This hook is reserved for forward migrations.
    return None


def _ensure_notes_column_size() -> None:
    tables = ["etl_run", "model_registry", "gold_label", "gold_set_snapshot"]
    with db_cursor() as (conn, cursor):
        for table in tables:
            rows = fetch_all(
                """
                SELECT DATA_TYPE
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND COLUMN_NAME = 'notes'
                """,
                (table,),
            )
            if rows and rows[0]["DATA_TYPE"] == "text":
                print(f"Upgrading {table}.notes from TEXT to MEDIUMTEXT...")
                cursor.execute(f"ALTER TABLE {table} MODIFY COLUMN notes MEDIUMTEXT DEFAULT NULL")
        conn.commit()


def init_schema() -> dict[str, str]:
    root_dir = Path(__file__).resolve().parents[3]
    schema_path = Path(os.getenv("ADDRESSFORGE_SCHEMA_PATH", root_dir / "sql" / "addressforge_schema.sql"))
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    
    try:
        execute_sql_script(schema_path)
    except Exception as exc:
        # Ignore "Table already exists" errors
        if "already exists" not in str(exc):
            raise
    
    _ensure_notes_column_size()
    _ensure_workspace_scoped_tables()
    _ensure_historical_replay_tables()
    _ensure_review_prescreen_table()
    ensure_etl_run_types()
    bootstrap_default_registry()
    return {"schema_path": str(schema_path), "status": "completed"}


def main() -> None:
    print(init_schema())


if __name__ == "__main__":
    main()
