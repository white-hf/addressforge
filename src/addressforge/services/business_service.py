from pathlib import Path
from datetime import datetime
import json
from addressforge.core.common import fetch_all, haversine_meters
from addressforge.core.config import ADDRESSFORGE_DATABASE, ADDRESSFORGE_WORKSPACE_NAME
from addressforge.core.utils import ttl_cache, generate_user_hash, simple_string_similarity


def _get_user_history_evidence(workspace_name: str, user_hash_key: str, base_address_key: str) -> dict[str, Any]:
    """
    Fetches the user's historical unit usage for a specific building.
    获取用户对特定建筑物的历史单元使用情况。
    """
    if not user_hash_key or not base_address_key:
        return {}
        
    query = """
        SELECT cu.unit_number, f.use_count
        FROM user_address_fact f
        JOIN canonical_unit cu ON f.unit_address_id = cu.unit_id
        JOIN canonical_building cb ON f.building_address_id = cb.building_id
        WHERE f.user_hash_key = %s 
          AND cb.building_key = %s
          AND cb.workspace_name = %s
        ORDER BY f.use_count DESC LIMIT 1
    """
    rows = fetch_all(query, (user_hash_key, base_address_key, workspace_name))
    return rows[0] if rows else {}


def _get_asset_evidence(workspace_name: str, base_address_key: str) -> dict[str, Any]:
    """
    Fetches canonical building data including its inferred type and known units.
    获取规范化的建筑物数据，包括其推断的类型和已知单元。
    """
    if not base_address_key:
        return {}
        
    query = """
        SELECT building_id, street_number, street_name, latitude, longitude, is_active
        FROM canonical_building
        WHERE building_key = %s AND workspace_name = %s
        LIMIT 1
    """
    rows = fetch_all(query, (base_address_key, workspace_name))
    if not rows:
        return {}
        
    building = rows[0]
    # Check if it has multiple units in canonical_unit
    units = fetch_all(
        "SELECT COUNT(*) as cnt FROM canonical_unit WHERE building_key = %s AND workspace_name = %s",
        (base_address_key, workspace_name)
    )
    building["has_known_units"] = bool(units and units[0]["cnt"] > 0)
    building["known_unit_count"] = units[0]["cnt"] if units else 0
    return building


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
    user_history_unit: str | None,
    asset_data: dict[str, Any],
) -> list[str]:
    """
    Classifies dirty addresses into strictly evidence-based categories (History, Asset, GPS).
    将脏地址分类为严格基于证据的类别（历史记录、资产、GPS）。
    """
    categories: list[str] = []
    
    # Rule 1. History Mismatch: User used units before at this building, but current is missing it
    # 规则 1. 历史不符：用户以前在该建筑使用过单元，但当前缺失
    if user_history_unit and not suggested_unit_number:
        categories.append("history_mismatch")
        
    # Rule 2. Asset Gap: Matches a known multi-unit building in asset library but missing unit
    # 规则 2. 资产库缺失：匹配资产库中已知的多单元建筑但缺失单元
    if asset_data.get("has_known_units") and not suggested_unit_number:
        if "history_mismatch" not in categories:
            categories.append("asset_gap")
            
    # Rule 3. Location Drift: GPS significantly differs from Asset center or History
    # 规则 3. 位置严重偏移：GPS 与资产中心或历史记录存在显著偏差
    if bool(hints.get("gps_drift_detected")):
        categories.append("location_drift")
        
    return categories


def list_dirty_address_diagnostics(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    *,
    source_name: str | None = None,
    batch_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Returns simplified dirty-address diagnostics based on deterministic evidence (assets, history).
    返回基于确定性证据（资产、历史记录）的简化脏地址诊断。
    """
    safe_limit = max(1, min(int(limit), 500))
    # Using the optimized composite index idx_cleaning_full_scan
    sql = """
        SELECT
            acr.raw_id,
            acr.raw_address_text,
            acr.decision,
            acr.confidence,
            acr.reason,
            acr.building_type,
            acr.suggested_unit_number,
            acr.base_address_key,
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
    # Fetch a larger sample to ensure we find enough rule-conforming rows
    # 获取更大的样本，以确保我们找到足够的符合规则的行
    params.append(min(safe_limit * 10, 2000)) 
    rows = fetch_all(sql, tuple(params))

    items: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {
        "history_mismatch": 0,
        "asset_gap": 0,
        "location_drift": 0,
    }

    for row in rows:
        validation = _json_dict(row.get("validation_json"))
        reference = _json_dict(row.get("reference_json"))
        parser_json = _json_dict(row.get("parser_json"))
        payload = _json_dict(row.get("source_payload"))
        
        raw_text = str(row.get("raw_address_text") or "").strip()
        base_key = str(row.get("base_address_key") or "").strip()
        
        # 1. Evidence: User History
        # 1. 证据：用户历史记录
        user_name = payload.get("consignee")
        user_phone = payload.get("mobile")
        user_hash = generate_user_hash(user_name, user_phone) if user_name and user_phone else None
        user_evidence = _get_user_history_evidence(workspace_name, user_hash, base_key) if user_hash else {}
        user_history_unit = user_evidence.get("unit_number")
        
        # 2. Evidence: Asset Library
        # 2. 证据：资产库
        asset_evidence = _get_asset_evidence(workspace_name, base_key)
        
        # 3. Guard: Hallucination Detection (Levenshtein/Jaccard)
        # 3. 守卫：幻觉检测
        best_candidate = parser_json.get("best_candidate") or {}
        parsed = best_candidate.get("parsed") or {}
        cand_sn = str(parsed.get("street_number") or "")
        cand_st = str(parsed.get("street_name") or "")
        
        is_hallucination = False
        if cand_sn and cand_sn not in raw_text:
            # If street number is completely missing from raw text (e.g. 123), it's a hallucination
            is_hallucination = True
        elif cand_st and simple_string_similarity(cand_st, raw_text) < 0.3:
            is_hallucination = True
            
        # 4. GPS Drift Calculation
        # 4. GPS 偏移计算
        gps_drift_m = 0.0
        gps_drift_detected = False
        curr_lat = row.get("latitude")
        curr_lon = row.get("longitude")
        if curr_lat and curr_lon and asset_evidence.get("latitude"):
            gps_drift_m = haversine_meters(
                float(curr_lat), float(curr_lon),
                float(asset_evidence["latitude"]), float(asset_evidence["longitude"])
            )
            if gps_drift_m > 250: # Threshold for drift
                gps_drift_detected = True

        decision = str(row.get("decision") or validation.get("decision") or "").strip().lower()
        building_type = str(row.get("building_type") or validation.get("building_type") or "").strip().lower()
        suggested_unit = row.get("suggested_unit_number")
        
        hints = (validation.get("hints") or {}).copy()
        hints["gps_drift_detected"] = gps_drift_detected
        hints["gps_drift_meters"] = gps_drift_m
        hints["is_hallucination"] = is_hallucination
        
        categories = _classify_dirty_categories(
            decision=decision,
            building_type=building_type,
            reason=str(row.get("reason") or ""),
            hints=hints,
            suggested_unit_number=suggested_unit,
            user_history_unit=user_history_unit,
            asset_data=asset_evidence,
        )
        
        if not categories:
            continue
            
        for cat in categories:
            if cat in category_counts:
                category_counts[cat] += 1

        items.append({
            "raw_id": row.get("raw_id"),
            "source_name": row.get("source_name"),
            "raw_address_text": raw_text,
            "decision": decision,
            "confidence": float(row.get("confidence") or validation.get("confidence") or 0.0),
            "building_type": building_type,
            "categories": categories,
            "primary_category": categories[0],
            "is_hallucination": is_hallucination,
            "evidence": {
                "user_history_unit": user_history_unit,
                "user_history_count": user_evidence.get("use_count"),
                "asset_found": bool(asset_evidence),
                "asset_known_units": asset_evidence.get("known_unit_count", 0),
                "gps_drift_meters": round(gps_drift_m, 1)
            },
            "suggested_address": {
                "street_number": cand_sn if not is_hallucination else None,
                "street_name": cand_st if not is_hallucination else None,
                "unit_number": suggested_unit or user_history_unit,
                "city": row.get("city"),
                "province": row.get("province"),
                "postal_code": row.get("postal_code"),
            },
            "updated_at": str(row.get("updated_at") or ""),
        })

        if len(items) >= safe_limit:
            break

    return {
        "workspace_name": workspace_name,
        "counts": {
            "total": len(items),
            "by_category": category_counts,
        },
        "items": items,
    }
