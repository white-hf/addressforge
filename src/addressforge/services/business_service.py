from pathlib import Path
from datetime import datetime
import json
from addressforge.core.common import fetch_all
from addressforge.core.config import ADDRESSFORGE_DATABASE, ADDRESSFORGE_WORKSPACE_NAME


def _table_has_column(table_name: str, column_name: str) -> bool:
    rows = fetch_all(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (ADDRESSFORGE_DATABASE, table_name, column_name),
    )
    return bool(rows and int(rows[0]["cnt"]) > 0)

def get_process_overview(workspace_name=ADDRESSFORGE_WORKSPACE_NAME):
    raw_rows = fetch_all("SELECT COUNT(*) AS cnt FROM raw_address_record WHERE workspace_name = %s", (workspace_name,))
    cleaning_rows = fetch_all("SELECT COUNT(*) AS cnt FROM address_cleaning_result WHERE workspace_name = %s", (workspace_name,))
    review_rows = fetch_all(
        "SELECT COUNT(*) AS cnt FROM active_learning_queue WHERE workspace_name = %s AND status = 'queued'",
        (workspace_name,),
    )
    if _table_has_column("canonical_building_address", "workspace_name"):
        building_rows = fetch_all("SELECT COUNT(*) AS cnt FROM canonical_building_address WHERE workspace_name = %s", (workspace_name,))
    else:
        building_rows = fetch_all("SELECT COUNT(*) AS cnt FROM canonical_building_address")
    if _table_has_column("canonical_unit_address", "workspace_name"):
        unit_rows = fetch_all("SELECT COUNT(*) AS cnt FROM canonical_unit_address WHERE workspace_name = %s", (workspace_name,))
    else:
        unit_rows = fetch_all("SELECT COUNT(*) AS cnt FROM canonical_unit_address")
    return {
        "stages": {
            "ingestion": {"label": "Data Inbound", "label_zh": "数据入库", "count": int(raw_rows[0]["cnt"]) if raw_rows else 0},
            "cleaning": {"label": "Governance", "label_zh": "地址治理", "count": int(cleaning_rows[0]["cnt"]) if cleaning_rows else 0},
            "review": {"label": "Review Lab", "label_zh": "专家审核", "pending": int(review_rows[0]["cnt"]) if review_rows else 0},
            "publish": {
                "label": "Assets",
                "label_zh": "资产发布",
                "count": (int(building_rows[0]["cnt"]) if building_rows else 0) + (int(unit_rows[0]["cnt"]) if unit_rows else 0),
            }
        }
    }

def get_business_dashboard_metrics(workspace_name=ADDRESSFORGE_WORKSPACE_NAME):
    eval_rows = fetch_all(
        """
        SELECT metrics_json
        FROM model_registry
        WHERE workspace_name = %s AND status = 'evaluated'
        ORDER BY updated_at DESC, model_id DESC
        LIMIT 3
        """,
        (workspace_name,),
    )
    accuracy_trend = []
    for row in reversed(eval_rows):
        try:
            metrics = json.loads(row.get("metrics_json") or "{}")
        except Exception:
            metrics = {}
        release = metrics.get("release_benchmark") or {}
        accuracy_trend.append(float(release.get("decision_f1") or metrics.get("metric_value") or 0.0))
    raw_rows = fetch_all("SELECT COUNT(*) AS cnt FROM raw_address_record WHERE workspace_name = %s", (workspace_name,))
    gold_rows = fetch_all(
        "SELECT COUNT(*) AS cnt FROM gold_label WHERE workspace_name = %s AND review_status = 'accepted' AND label_source = 'human'",
        (workspace_name,),
    )
    return {
        "accuracy_trend": accuracy_trend,
        "avg_review_time_sec": None,
        "daily_processing_volume": int(raw_rows[0]["cnt"]) if raw_rows else 0,
        "gold_set_growth": int(gold_rows[0]["cnt"]) if gold_rows else 0,
    }

def get_batch_stats(workspace_name=ADDRESSFORGE_WORKSPACE_NAME):
    pending_rows = fetch_all(
        "SELECT COUNT(*) AS cnt FROM active_learning_queue WHERE workspace_name = %s AND status = 'queued'",
        (workspace_name,),
    )
    exported_rows = fetch_all(
        "SELECT COUNT(*) AS cnt FROM active_learning_queue WHERE workspace_name = %s AND status = 'exported'",
        (workspace_name,),
    )
    snapshot_rows = fetch_all(
        """
        SELECT snapshot_id, gold_set_version, created_at
        FROM gold_set_snapshot
        WHERE workspace_name = %s
        ORDER BY created_at DESC, snapshot_id DESC
        LIMIT 3
        """,
        (workspace_name,),
    )
    active_batch_id = snapshot_rows[0]["snapshot_id"] if snapshot_rows else None
    current_gold_version = snapshot_rows[0]["gold_set_version"] if snapshot_rows else None
    return {
        "pending_total": int(pending_rows[0]["cnt"]) if pending_rows else 0,
        "finished_unfrozen": int(exported_rows[0]["cnt"]) if exported_rows else 0,
        "active_batch_id": active_batch_id,
        "current_gold_version": current_gold_version,
        "history": [
            {
                "batch_id": row["snapshot_id"],
                "created_at": str(row["created_at"]),
                "size": None,
                "status": "active" if idx == 0 else "completed",
            }
            for idx, row in enumerate(snapshot_rows)
        ]
    }

def get_reports_list(workspace_name=ADDRESSFORGE_WORKSPACE_NAME):
    # 报表列表与摘要
    # 扫描 runtime/reports 目录
    report_dir = Path("runtime/reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    
    files = []
    for f in report_dir.glob("*.*"):
        if f.suffix in ['.md', '.pdf', '.csv']:
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
            size_kb = round(f.stat().st_size / 1024, 1)
            files.append({
                "name": f.name,
                "path": str(f),
                "created_at": mtime,
                "size": f"{size_kb} KB"
            })
    
    # 按时间降序排序
    files.sort(key=lambda x: x["created_at"], reverse=True)
    
    return {
        "summaries": {
            "quality": files[0]["created_at"] if files else "-",
            "evaluation": "-",
            "gold": "-",
            "building": "-"
        },
        "files": files[:10]
    }
