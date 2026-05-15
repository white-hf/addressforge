from pathlib import Path
from datetime import datetime
import json
from addressforge.core.common import fetch_all
from addressforge.core.config import ADDRESSFORGE_DATABASE, ADDRESSFORGE_WORKSPACE_NAME
from addressforge.core.utils import ttl_cache


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

@ttl_cache(seconds=300)
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

@ttl_cache(seconds=300)
def get_business_dashboard_metrics(workspace_name=ADDRESSFORGE_WORKSPACE_NAME):
    # Optimization: Show the Promoted model's accuracy first, then the latest evaluated ones
    # 优化：优先显示已提升模型的准确率，然后是最近评测的模型
    eval_rows = fetch_all(
        """
        SELECT metrics_json, status
        FROM model_registry
        WHERE workspace_name = %s 
          AND status IN ('promoted', 'evaluated')
        ORDER BY (status = 'promoted') DESC, updated_at DESC, model_id DESC
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

@ttl_cache(seconds=300)
def get_asset_stats(workspace_name=ADDRESSFORGE_WORKSPACE_NAME):
    """
    Retrieves statistics about canonical assets (buildings and units).
    获取规范资产（建筑物和单元）的统计信息。
    """
    building_rows = fetch_all(
        "SELECT COUNT(*) AS cnt FROM canonical_building_address"
    )
    unit_rows = fetch_all(
        "SELECT COUNT(*) AS cnt FROM canonical_unit_address"
    )
    return {
        "total_buildings": int(building_rows[0]["cnt"]) if building_rows else 0,
        "total_units": int(unit_rows[0]["cnt"]) if unit_rows else 0,
    }


@ttl_cache(seconds=60)
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

@ttl_cache(seconds=30)
def get_reports_list(workspace_name=ADDRESSFORGE_WORKSPACE_NAME):
    """
    Retrieves the list of reports and computes specific summaries per report type.
    获取报表列表并计算每种报表类型的特定摘要。
    """
    report_dir = Path("runtime/reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    
    def get_latest_mtime(pattern: str) -> str:
        files = list(report_dir.glob(pattern))
        if not files:
            return "-"
        latest_file = max(files, key=lambda f: f.stat().st_mtime)
        return datetime.fromtimestamp(latest_file.stat().st_mtime).strftime('%Y-%m-%d %H:%M')

    summaries = {
        "quality": get_latest_mtime("*quality*.md"),
        "evaluation": get_latest_mtime("*release_report.md"),
        "gold": get_latest_mtime("*gold_governance*.md"),
        "building": get_latest_mtime("*building*.md"),
        "shadow": get_latest_mtime("*shadow_report.md")
    }

    files = []
    for f in report_dir.glob("*.*"):
        if f.suffix in ['.md', '.pdf', '.csv', '.json']:
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
            size_kb = round(f.stat().st_size / 1024, 1)
            files.append({
                "name": f.name,
                "path": str(f),
                "created_at": mtime,
                "size": f"{size_kb} KB"
            })
    
    # Sort descending by time
    # 按时间降序排序
    files.sort(key=lambda x: x["created_at"], reverse=True)
    
    return {
        "summaries": summaries,
        "files": files[:20]
    }


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except Exception:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _pick_first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _classify_dirty_categories(
    *,
    decision: str,
    building_type: str,
    reason: str,
    hints: dict[str, Any],
    suggested_unit_number: str | None,
    reference_json: dict[str, Any],
) -> list[str]:
    categories: list[str] = []
    reason_text = reason.lower()
    if decision == "enrich" and (
        "unit may be missing" in reason_text
        or (
            building_type == "multi_unit"
            and not suggested_unit_number
            and bool(reference_json.get("reference_unit_numbers"))
        )
    ):
        categories.append("missing_unit")
    if bool(hints.get("gps_conflict")):
        categories.append("gps_conflict")
    if str(hints.get("reference_gap_reason") or "").strip():
        categories.append("reference_gap")
    if bool(hints.get("parser_disagreement")):
        categories.append("parser_disagreement")
    if decision == "review":
        categories.append("manual_review")
    if decision == "reject":
        categories.append("reject")
    return categories


def list_dirty_address_diagnostics(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    *,
    source_name: str | None = None,
    batch_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Returns dirty-address diagnostics for newly cleaned data.
    返回新清洗数据中的脏地址诊断列表，支持按 source_name / batch_id 过滤。
    """
    safe_limit = max(1, min(int(limit), 500))
    sql = """
        SELECT
            acr.raw_id,
            acr.raw_address_text,
            acr.decision,
            acr.confidence,
            acr.reason,
            acr.building_type,
            acr.suggested_unit_number,
            acr.validation_json,
            acr.reference_json,
            acr.parser_json,
            r.source_name,
            r.city,
            r.province,
            r.postal_code,
            r.country_code,
            r.latitude,
            r.longitude,
            r.source_payload,
            JSON_UNQUOTE(JSON_EXTRACT(r.source_payload, '$.batch_id')) AS batch_id,
            acr.updated_at
        FROM address_cleaning_result acr
        JOIN raw_address_record r
          ON acr.raw_id = r.raw_id
        WHERE acr.workspace_name = %s
          AND r.workspace_name = %s
          AND acr.checkpoint_status = 'completed'
          AND (
                acr.decision IN ('enrich', 'review', 'reject')
                OR acr.validation_json IS NOT NULL
              )
    """
    params: list[Any] = [workspace_name, workspace_name]
    if source_name:
        sql += " AND r.source_name = %s"
        params.append(source_name)
    if batch_id:
        sql += " AND JSON_UNQUOTE(JSON_EXTRACT(r.source_payload, '$.batch_id')) = %s"
        params.append(str(batch_id))
    sql += " ORDER BY acr.updated_at DESC, acr.raw_id DESC LIMIT %s"
    params.append(max(safe_limit * 4, 200))
    rows = fetch_all(sql, tuple(params))

    items: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {
        "missing_unit": 0,
        "gps_conflict": 0,
        "reference_gap": 0,
        "parser_disagreement": 0,
        "manual_review": 0,
        "reject": 0,
    }
    for row in rows:
        validation = _json_dict(row.get("validation_json"))
        reference = _json_dict(row.get("reference_json"))
        parser_json = _json_dict(row.get("parser_json"))
        hints = validation.get("hints") if isinstance(validation.get("hints"), dict) else {}
        canonical = validation.get("canonical") if isinstance(validation.get("canonical"), dict) else {}
        parsed = (
            parser_json.get("best_candidate", {}).get("parsed")
            if isinstance(parser_json.get("best_candidate"), dict)
            else {}
        ) or {}
        decision = str(row.get("decision") or validation.get("decision") or "").strip().lower()
        building_type = str(row.get("building_type") or validation.get("building_type") or "").strip().lower()
        reason = str(row.get("reason") or validation.get("reason") or "").strip()
        suggested_unit_number = _pick_first_non_empty(
            row.get("suggested_unit_number"),
            validation.get("suggested_unit_number"),
            canonical.get("unit_number"),
            (reference.get("reference_unit_numbers") or [None])[0] if isinstance(reference.get("reference_unit_numbers"), list) else None,
        )
        categories = _classify_dirty_categories(
            decision=decision,
            building_type=building_type,
            reason=reason,
            hints=hints,
            suggested_unit_number=suggested_unit_number,
            reference_json=reference,
        )
        if not categories:
            continue
        for category in categories:
            category_counts[category] = category_counts.get(category, 0) + 1
        items.append(
            {
                "raw_id": row.get("raw_id"),
                "source_name": row.get("source_name"),
                "batch_id": _pick_first_non_empty(row.get("batch_id")),
                "raw_address_text": row.get("raw_address_text"),
                "decision": decision,
                "confidence": float(row.get("confidence") or validation.get("confidence") or 0.0),
                "reason": reason,
                "building_type": building_type,
                "categories": categories,
                "primary_category": categories[0],
                "suggested_unit_number": suggested_unit_number,
                "suggested_address": {
                    "street_number": _pick_first_non_empty(canonical.get("street_number"), parsed.get("street_number")),
                    "street_name": _pick_first_non_empty(canonical.get("street_name"), parsed.get("street_name")),
                    "unit_number": suggested_unit_number,
                    "city": _pick_first_non_empty(canonical.get("city"), row.get("city"), parsed.get("city")),
                    "province": _pick_first_non_empty(canonical.get("province"), row.get("province"), parsed.get("province")),
                    "postal_code": _pick_first_non_empty(canonical.get("postal_code"), row.get("postal_code"), parsed.get("postal_code")),
                    "country_code": _pick_first_non_empty(canonical.get("country_code"), row.get("country_code"), "CA"),
                },
                "hints": {
                    "gps_conflict": bool(hints.get("gps_conflict")),
                    "reference_score": hints.get("reference_score"),
                    "reference_gap_reason": hints.get("reference_gap_reason"),
                    "parser_disagreement": bool(hints.get("parser_disagreement")),
                    "reference_available": bool(hints.get("reference_available") or reference),
                },
                "reference": {
                    "external_id": reference.get("external_id"),
                    "reference_unit_numbers": reference.get("reference_unit_numbers") or [],
                },
                "updated_at": str(row.get("updated_at") or ""),
            }
        )
        if len(items) >= safe_limit:
            break
    return {
        "workspace_name": workspace_name,
        "filters": {
            "source_name": source_name,
            "batch_id": batch_id,
            "limit": safe_limit,
        },
        "counts": {
            "total": len(items),
            "by_category": category_counts,
        },
        "items": items,
    }
