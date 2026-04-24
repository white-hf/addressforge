from __future__ import annotations

import os
from pathlib import Path

from addressforge.core.common import execute_sql_script


def main() -> None:
    root_dir = Path(__file__).resolve().parents[3]
    schema_path = Path(os.getenv("ADDRESSFORGE_SCHEMA_PATH", root_dir / "sql" / "addressforge_schema.sql"))
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    execute_sql_script(schema_path)
    print({"schema_path": str(schema_path), "status": "completed"})


if __name__ == "__main__":
    main()
