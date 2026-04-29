from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from addressforge.core.common import create_run, db_cursor, dumps_payload, finish_run, fetch_all
from addressforge.core.config import ADDRESSFORGE_EXPORT_DIR, ADDRESSFORGE_WORKSPACE_NAME
from addressforge.core.utils import logger


@dataclass(frozen=True)
class ExportedTable:
    table_name: str
    file_path: str
    row_count: int


def _artifact_dir(root_dir: str | None, workspace_name: str, run_id: int) -> Path:
    base = Path(root_dir or ADDRESSFORGE_EXPORT_DIR).expanduser()
    if not base.is_absolute():
        base = Path(__file__).resolve().parents[3] / base
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return base / workspace_name / f"workspace_export_{stamp}_run_{run_id}"


def list_workspace_exports(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME, export_root: str | None = None) -> list[dict[str, Any]]:
    base = Path(export_root or ADDRESSFORGE_EXPORT_DIR).expanduser()
    if not base.is_absolute():
        base = Path(__file__).resolve().parents[3] / base
    base = base / workspace_name
    if not base.exists():
        return []
    exports: list[dict[str, Any]] = []
    for manifest_path in sorted(base.glob("*/manifest.json"), reverse=True):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        exports.append(
            {
                "manifest_path": str(manifest_path),
                "export_dir": manifest.get("export_dir") or str(manifest_path.parent),
                "run_id": manifest.get("run_id"),
                "created_at": manifest.get("created_at"),
                "total_rows": manifest.get("total_rows"),
                "tables": manifest.get("tables") or [],
            }
        )
    return exports


def _write_query_to_csv(path: Path, query: str, params: Iterable[Any] | None = None, chunk_size: int = 1000) -> int:
    row_count = 0
    with db_cursor(dictionary=True) as (_, cursor):
        cursor.execute(query, params or ())
        fieldnames = [str(name) for name in (cursor.column_names or [])]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            while True:
                rows = cursor.fetchmany(chunk_size)
                if not rows:
                    break
                for row in rows:
                    serializable = {key: (json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value) for key, value in row.items()}
                    writer.writerow(serializable)
                    row_count += 1
    return row_count


def export_workspace_snapshot(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    export_root: str | None = None,
) -> dict[str, Any]:
    run_id = create_run("ml_export", notes=f"workspace_snapshot workspace={workspace_name}")
    try:
        export_dir = _artifact_dir(export_root, workspace_name, run_id)
        export_dir.mkdir(parents=True, exist_ok=True)

        tables = [
            (
                "workspace_registry.csv",
                "SELECT * FROM workspace_registry WHERE workspace_name = %s ORDER BY workspace_id ASC",
                (workspace_name,),
            ),
            (
                "model_registry.csv",
                "SELECT * FROM model_registry WHERE workspace_name = %s ORDER BY model_id ASC",
                (workspace_name,),
            ),
            (
                "control_setting.csv",
                "SELECT * FROM control_setting WHERE workspace_name = %s ORDER BY setting_id ASC",
                (workspace_name,),
            ),
            (
                "control_job.csv",
                "SELECT * FROM control_job WHERE workspace_name = %s ORDER BY job_id ASC",
                (workspace_name,),
            ),
            (
                "raw_address_record.csv",
                "SELECT * FROM raw_address_record WHERE workspace_name = %s ORDER BY raw_id ASC",
                (workspace_name,),
            ),
            (
                "address_cleaning_result.csv",
                "SELECT * FROM address_cleaning_result WHERE workspace_name = %s ORDER BY result_id ASC",
                (workspace_name,),
            ),
        ]

        exported: list[ExportedTable] = []
        total_rows = 0
        for filename, query, params in tables:
            output_path = export_dir / filename
            count = _write_query_to_csv(output_path, query, params=params)
            exported.append(ExportedTable(table_name=filename.replace(".csv", ""), file_path=str(output_path), row_count=count))
            total_rows += count

        ref_path = export_dir / "external_building_reference.csv"
        try:
            ref_count = _write_query_to_csv(
                ref_path,
                "SELECT * FROM external_building_reference WHERE workspace_name = %s ORDER BY reference_id ASC",
                params=(workspace_name,),
            )
        except Exception:
            ref_count = _write_query_to_csv(
                ref_path,
                "SELECT * FROM external_building_reference ORDER BY reference_id ASC",
            )
        exported.append(
            ExportedTable(table_name="external_building_reference", file_path=str(ref_path), row_count=ref_count)
        )
        total_rows += ref_count

        manifest = {
            "run_id": run_id,
            "workspace_name": workspace_name,
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "export_dir": str(export_dir),
            "total_rows": total_rows,
            "tables": [asdict(item) for item in exported],
        }
        manifest_path = export_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        finish_run(
            run_id,
            "completed",
            notes=dumps_payload(
                {
                    "workspace_name": workspace_name,
                    "export_dir": str(export_dir),
                    "manifest_path": str(manifest_path),
                    "total_rows": total_rows,
                }
            ),
        )
        logger.info(
            "Workspace export completed: run_id=%s workspace=%s rows=%s dir=%s",
            run_id,
            workspace_name,
            total_rows,
            export_dir,
        )
        return {
            "run_id": run_id,
            "workspace_name": workspace_name,
            "export_dir": str(export_dir),
            "manifest_path": str(manifest_path),
            "total_rows": total_rows,
            "tables": [asdict(item) for item in exported],
        }
    except Exception as exc:
        finish_run(run_id, "failed", notes=dumps_payload({"error": str(exc)}))
        raise
