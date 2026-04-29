from __future__ import annotations

import json
from typing import Any

from addressforge.core.common import db_cursor, fetch_all


def list_settings(workspace_name: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM control_setting WHERE 1=1"
    params: list[Any] = []
    if workspace_name:
        query += " AND workspace_name = %s"
        params.append(workspace_name)
    query += " ORDER BY workspace_name ASC, setting_key ASC"
    return fetch_all(query, tuple(params))


def get_setting(workspace_name: str, setting_key: str, default: Any | None = None) -> Any:
    rows = fetch_all(
        """
        SELECT setting_value
        FROM control_setting
        WHERE workspace_name = %s AND setting_key = %s
        LIMIT 1
        """,
        (workspace_name, setting_key),
    )
    if not rows:
        return default
    value = rows[0].get("setting_value")
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return text


def set_setting(workspace_name: str, setting_key: str, setting_value: Any) -> dict[str, Any]:
    if isinstance(setting_value, (dict, list)):
        raw_value = json.dumps(setting_value, ensure_ascii=False)
    elif isinstance(setting_value, bool):
        raw_value = "true" if setting_value else "false"
    elif setting_value is None:
        raw_value = ""
    else:
        raw_value = str(setting_value)
    with db_cursor() as (conn, cursor):
        cursor.execute(
            """
            INSERT INTO control_setting (workspace_name, setting_key, setting_value)
            VALUES (%s, %s, %s) AS new_row
            ON DUPLICATE KEY UPDATE
                setting_value = new_row.setting_value,
                updated_at = NOW()
            """,
            (workspace_name, setting_key, raw_value),
        )
        conn.commit()
    return {
        "workspace_name": workspace_name,
        "setting_key": setting_key,
        "setting_value": setting_value,
    }
