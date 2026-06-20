from fastapi import APIRouter, HTTPException
from addressforge.services.cleaning_service import enqueue_cleaning
from pydantic import BaseModel
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME

router = APIRouter()

class CleaningRequest(BaseModel):
    workspace_name: str = None
    batch_size: int = 1000
    preview_limit: int = 100
    opportunity_limit: int = 3
    requested_by: str = None
    notes: str = None
    source_name: str | None = None
    batch_id: str | None = None
    target_buckets: list[str] | None = None


def _review_backlog_filter(request: CleaningRequest) -> tuple[str, list[str]]:
    workspace = request.workspace_name or ADDRESSFORGE_WORKSPACE_NAME
    where_clauses = ['acr.decision = "review"', 'acr.workspace_name = %s']
    params: list[str] = [workspace]
    if request.source_name:
        where_clauses.append("rar.source_name = %s")
        params.append(request.source_name)
    if request.batch_id:
        where_clauses.append('JSON_UNQUOTE(JSON_EXTRACT(rar.source_payload, "$.batch_id")) = %s')
        params.append(request.batch_id)
    return " AND ".join(where_clauses), params


def _current_batch_filter(request: CleaningRequest) -> tuple[str, list[str]]:
    workspace = request.workspace_name or ADDRESSFORGE_WORKSPACE_NAME
    where_clauses = ['acr.workspace_name = %s']
    params: list[str] = [workspace]
    if request.source_name:
        where_clauses.append("rar.source_name = %s")
        params.append(request.source_name)
    if request.batch_id:
        where_clauses.append('JSON_UNQUOTE(JSON_EXTRACT(rar.source_payload, "$.batch_id")) = %s')
        params.append(request.batch_id)
    return " AND ".join(where_clauses), params


def _fetch_review_opportunity_items(workspace: str, source_name: str | None, limit: int) -> list[dict[str, object]]:
    from addressforge.core.common import fetch_all

    where_clauses = ['acr.workspace_name = %s']
    params: list[str] = [workspace]
    if source_name:
        where_clauses.append("rar.source_name = %s")
        params.append(source_name)
    where_clauses.append('JSON_EXTRACT(rar.source_payload, "$.batch_id") IS NOT NULL')
    where_sql = " AND ".join(where_clauses)

    rows = fetch_all(
        f"""
        SELECT
            rar.source_name,
            JSON_UNQUOTE(JSON_EXTRACT(rar.source_payload, "$.batch_id")) AS batch_id,
            COUNT(*) AS total_rows,
            SUM(CASE WHEN acr.decision = 'review' THEN 1 ELSE 0 END) AS review_count,
            SUM(CASE WHEN acr.decision = 'accept' THEN 1 ELSE 0 END) AS accept_count,
            SUM(CASE WHEN acr.decision = 'enrich' THEN 1 ELSE 0 END) AS enrich_count,
            SUM(CASE WHEN acr.decision = 'pending' OR acr.decision IS NULL THEN 1 ELSE 0 END) AS pending_count
        FROM address_cleaning_result acr
        JOIN raw_address_record rar
          ON rar.workspace_name = acr.workspace_name
         AND rar.raw_id = acr.raw_id
        WHERE {where_sql}
        GROUP BY rar.source_name, JSON_UNQUOTE(JSON_EXTRACT(rar.source_payload, "$.batch_id"))
        HAVING review_count > 0
        ORDER BY review_count DESC, total_rows DESC
        LIMIT {limit}
        """,
        tuple(params),
    )

    items: list[dict[str, object]] = []
    for row in rows:
        total_rows = int(row.get("total_rows") or 0)
        review_count = int(row.get("review_count") or 0)
        accept_count = int(row.get("accept_count") or 0)
        enrich_count = int(row.get("enrich_count") or 0)
        pending_count = int(row.get("pending_count") or 0)
        items.append(
            {
                "source_name": row.get("source_name"),
                "batch_id": row.get("batch_id"),
                "total_rows": total_rows,
                "review_count": review_count,
                "accept_count": accept_count,
                "enrich_count": enrich_count,
                "pending_count": pending_count,
                "review_rate": round((review_count / total_rows), 4) if total_rows else 0.0,
            }
        )
    return items


def _build_targeted_review_preview(
    workspace: str,
    selected_batches: list[dict[str, str]],
    sample_limit: int,
    custom_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from addressforge.core.common import fetch_all
    from addressforge.api.server import AddressPlatformService, AddressRequest

    if not selected_batches and not custom_rows:
        return {
            "sampled_rows": 0,
            "decision_counts": {"accept": 0, "enrich": 0, "review": 0},
            "transition_counts": {},
            "reason_counts": {},
            "projected_recovery_count": 0,
            "projected_remaining_review_count": 0,
            "projected_recovery_rate": 0.0,
            "projected_remaining_review_rate": 0.0,
            "samples": [],
        }

    rows = custom_rows
    if not rows:
        batch_filters: list[str] = []
        batch_params: list[str] = []
        for item in selected_batches:
            batch_filters.append(
                '(rar.source_name = %s AND JSON_UNQUOTE(JSON_EXTRACT(rar.source_payload, "$.batch_id")) = %s)'
            )
            batch_params.extend([item["source_name"], item["batch_id"]])

        rows = fetch_all(
            f"""
            SELECT acr.raw_id, acr.raw_address_text, rar.source_name,
                JSON_UNQUOTE(JSON_EXTRACT(rar.source_payload, "$.batch_id")) AS batch_id,
                rar.city, rar.province, rar.postal_code, rar.country_code
            FROM address_cleaning_result acr
            JOIN raw_address_record rar
            ON rar.workspace_name = acr.workspace_name
            AND rar.raw_id = acr.raw_id
            WHERE acr.decision = "review"
            AND acr.workspace_name = %s
            AND ({' OR '.join(batch_filters)})
            ORDER BY acr.raw_id DESC
            LIMIT {sample_limit}
            """,
            tuple([workspace, *batch_params]),
        )

    service = AddressPlatformService()
    decision_counts: dict[str, int] = {}
    transition_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    samples: list[dict[str, object]] = []
    for row in rows:
        result = service.validate(AddressRequest(raw_address_text=row["raw_address_text"]))
        decision = str(result.get("decision") or "unknown")
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
        transition_key = f"review->{decision}"
        transition_counts[transition_key] = transition_counts.get(transition_key, 0) + 1
        reason = str(result.get("reason") or "")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if len(samples) < 20 and decision != "review":
            samples.append(
                {
                    "raw_id": row["raw_id"],
                    "raw_address_text": row["raw_address_text"],
                    "source_name": row.get("source_name"),
                    "batch_id": row.get("batch_id"),
                    "decision": decision,
                    "reason": reason,
                    "building_type": result.get("building_type"),
                    "suggested_unit_number": result.get("suggested_unit_number"),
                }
            )

    sampled_rows = len(rows)
    projected_recovery_count = int(decision_counts.get("accept", 0) + decision_counts.get("enrich", 0))
    projected_remaining_review_count = int(decision_counts.get("review", 0))
    return {
        "sampled_rows": sampled_rows,
        "decision_counts": decision_counts,
        "transition_counts": transition_counts,
        "reason_counts": reason_counts,
        "projected_recovery_count": projected_recovery_count,
        "projected_remaining_review_count": projected_remaining_review_count,
        "projected_recovery_rate": round((projected_recovery_count / sampled_rows), 4) if sampled_rows else 0.0,
        "projected_remaining_review_rate": round((projected_remaining_review_count / sampled_rows), 4) if sampled_rows else 0.0,
        "samples": samples,
    }


def _build_batch_recovery_summaries(
    workspace: str,
    selected_batches: list[dict[str, object]],
    sample_limit: int,
) -> list[dict[str, object]]:
    if not selected_batches:
        return []

    per_batch_limit = max(1, min(int(sample_limit or 100) // max(len(selected_batches), 1), sample_limit or 100))
    summaries: list[dict[str, object]] = []
    for item in selected_batches:
        batch_key = {
            "source_name": str(item.get("source_name") or ""),
            "batch_id": str(item.get("batch_id") or ""),
        }
        preview = _build_targeted_review_preview(workspace, [batch_key], per_batch_limit)
        summaries.append(
            {
                **batch_key,
                "leaderboard_total_rows": int(item.get("total_rows") or 0),
                "leaderboard_review_count": int(item.get("review_count") or 0),
                "leaderboard_accept_count": int(item.get("accept_count") or 0),
                "leaderboard_enrich_count": int(item.get("enrich_count") or 0),
                "leaderboard_pending_count": int(item.get("pending_count") or 0),
                "leaderboard_review_rate": float(item.get("review_rate") or 0.0),
                **preview,
            }
        )
    return summaries

@router.post("/trigger")
async def trigger(request: CleaningRequest):
    return {"status": "queued", "job": enqueue_cleaning(request.workspace_name, request.batch_size, request.requested_by, request.notes)}

@router.post("/reclean-reviews")
async def reclean_reviews(request: CleaningRequest):
    """
    Resets all 'review' status records to 'pending' to force re-evaluation with the latest ML models.
    将所有“审核 (review)”状态的记录重置为“待定 (pending)”，以强制使用最新的 ML 模型重新评估。
    """
    from addressforge.core.common import db_cursor
    workspace = request.workspace_name or ADDRESSFORGE_WORKSPACE_NAME
    where_sql, params = _review_backlog_filter(request)
    
    with db_cursor() as (conn, cursor):
        cursor.execute(
            f"""
            SELECT MIN(acr.raw_id) as min_id
            FROM address_cleaning_result acr
            JOIN raw_address_record rar
              ON rar.workspace_name = acr.workspace_name
             AND rar.raw_id = acr.raw_id
            WHERE {where_sql}
            """,
            tuple(params)
        )
        first_review_row = cursor.fetchone() or {}
        min_id = first_review_row.get("min_id")

        # 1. Reset review records
        cursor.execute(
            f"""
            UPDATE address_cleaning_result acr
            JOIN raw_address_record rar
              ON rar.workspace_name = acr.workspace_name
             AND rar.raw_id = acr.raw_id
            SET acr.decision = "pending", acr.validation_json = NULL
            WHERE {where_sql}
            """,
            tuple(params)
        )
        affected = cursor.rowcount

        # 2. Roll back only to the earliest row that was previously in review,
        # rather than any unrelated pending row in the workspace.
        if min_id:
            cursor.execute(
                'UPDATE control_setting SET setting_value = %s WHERE setting_key = "cleaning.publish.last_raw_id" AND workspace_name = %s',
                (str(min_id - 1), workspace)
            )
        conn.commit()
    
    # 3. Trigger a cleaning job immediately
    job = enqueue_cleaning(workspace, request.batch_size, request.requested_by, "Triggered via Re-clean Reviews UI")
    
    return {
        "status": "success", 
        "affected_records": affected,
        "rolled_back_to": min_id,
        "source_name": request.source_name,
        "batch_id": request.batch_id,
        "job": job
    }


@router.post("/reclean-reviews-preview")
async def preview_reclean_reviews(request: CleaningRequest):
    """
    Previews how many review rows are likely to convert under the latest runtime
    without mutating the database.
    预估在最新运行时逻辑下，当前 review 积压中有多少行可能发生决策变化，不修改数据库。
    """
    workspace = request.workspace_name or ADDRESSFORGE_WORKSPACE_NAME
    where_sql, params = _review_backlog_filter(request)
    sample_limit = max(1, min(int(request.preview_limit or 100), 500))
    from addressforge.core.common import fetch_all
    rows = fetch_all(
        f"""
        SELECT acr.raw_id, acr.raw_address_text, rar.source_name,
               JSON_UNQUOTE(JSON_EXTRACT(rar.source_payload, "$.batch_id")) AS batch_id
        FROM address_cleaning_result acr
        JOIN raw_address_record rar
          ON rar.workspace_name = acr.workspace_name
         AND rar.raw_id = acr.raw_id
        WHERE {where_sql}
        ORDER BY acr.raw_id DESC
        LIMIT {sample_limit}
        """,
        tuple(params),
    )
    from addressforge.api.server import AddressPlatformService, AddressRequest
    service = AddressPlatformService()
    decision_counts: dict[str, int] = {}
    transition_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    samples: list[dict[str, object]] = []
    for row in rows:
        result = service.validate(AddressRequest(raw_address_text=row["raw_address_text"]))
        decision = str(result.get("decision") or "unknown")
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
        transition_key = f"review->{decision}"
        transition_counts[transition_key] = transition_counts.get(transition_key, 0) + 1
        reason = str(result.get("reason") or "")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if len(samples) < 20 and decision != "review":
            samples.append(
                {
                    "raw_id": row["raw_id"],
                    "raw_address_text": row["raw_address_text"],
                    "source_name": row.get("source_name"),
                    "batch_id": row.get("batch_id"),
                    "decision": decision,
                    "reason": reason,
                    "building_type": result.get("building_type"),
                    "suggested_unit_number": result.get("suggested_unit_number"),
                }
            )
    sampled_rows = len(rows)
    projected_recovery_count = int(decision_counts.get("accept", 0) + decision_counts.get("enrich", 0))
    projected_remaining_review_count = int(decision_counts.get("review", 0))
    return {
        "status": "success",
        "workspace_name": workspace,
        "source_name": request.source_name,
        "batch_id": request.batch_id,
        "preview_limit": sample_limit,
        "sampled_rows": sampled_rows,
        "decision_counts": decision_counts,
        "transition_counts": transition_counts,
        "reason_counts": reason_counts,
        "projected_recovery_count": projected_recovery_count,
        "projected_remaining_review_count": projected_remaining_review_count,
        "projected_recovery_rate": round((projected_recovery_count / sampled_rows), 4) if sampled_rows else 0.0,
        "projected_remaining_review_rate": round((projected_remaining_review_count / sampled_rows), 4) if sampled_rows else 0.0,
        "samples": samples,
    }


@router.post("/preview-top-review-opportunities")
async def preview_top_review_opportunities(request: CleaningRequest):
    """
    Aggregates the projected reclean impact for the top review-heavy batches so operators
    can decide whether bulk replay is worth running.
    聚合预估 top review-heavy 批次的重清洗收益，帮助运营判断是否值得批量回放。
    """
    workspace = request.workspace_name or ADDRESSFORGE_WORKSPACE_NAME
    limit = max(1, min(int(request.opportunity_limit or 3), 20))
    sample_limit = max(1, min(int(request.preview_limit or 100), 500))
    
    items = _fetch_review_opportunity_items(workspace, request.source_name, limit)
    selected = [
        item
        for item in items
        if item.get("source_name") and item.get("batch_id")
    ]
    
    if not selected:
        return {
            "status": "success",
            "workspace_name": workspace,
            "batch_summaries": [],
            "sampled_rows": 0,
            "projected_recovery_rate": 0.0
        }

    # Build detailed per-batch summaries
    # 构建详细的各批次摘要
    batch_summaries = _build_batch_recovery_summaries(workspace, selected, sample_limit)
    
    # Calculate aggregate metrics from batch summaries for consistency
    # 从批次摘要中计算聚合指标以保持一致性
    total_sampled = sum(int(s.get("sampled_rows") or 0) for s in batch_summaries)
    total_accept = sum(int(s.get("decision_counts", {}).get("accept", 0)) for s in batch_summaries)
    total_enrich = sum(int(s.get("decision_counts", {}).get("enrich", 0)) for s in batch_summaries)
    total_review = sum(int(s.get("decision_counts", {}).get("review", 0)) for s in batch_summaries)
    
    projected_recovery_count = total_accept + total_enrich
    
    # Merge reason counts from all batches
    # 合并所有批次的错误原因统计
    aggregate_reasons: dict[str, int] = {}
    for s in batch_summaries:
        for r, c in s.get("reason_counts", {}).items():
            aggregate_reasons[r] = aggregate_reasons.get(r, 0) + c

    return {
        "status": "success",
        "workspace_name": workspace,
        "source_name": request.source_name,
        "opportunity_limit": limit,
        "preview_limit": sample_limit,
        "selected_batches": [
            {"source_name": str(item.get("source_name") or ""), "batch_id": str(item.get("batch_id") or "")}
            for item in selected
        ],
        "batch_summaries": batch_summaries,
        "sampled_rows": total_sampled,
        "decision_counts": {
            "accept": total_accept,
            "enrich": total_enrich,
            "review": total_review
        },
        "reason_counts": aggregate_reasons,
        "projected_recovery_count": projected_recovery_count,
        "projected_recovery_rate": round(projected_recovery_count / total_sampled, 4) if total_sampled else 0.0,
        "projected_remaining_review_rate": round(total_review / total_sampled, 4) if total_sampled else 0.0,
    }


@router.post("/reclean-reviews-evidence")
async def reclean_reviews_evidence(request: CleaningRequest):
    """
    Returns the current decision distribution for a filtered batch/source so operators
    can verify post-reclean impact.
    返回筛选批次/来源的当前决策分布，用于验证重清洗后的真实效果。
    """
    from addressforge.core.common import fetch_all

    workspace = request.workspace_name or ADDRESSFORGE_WORKSPACE_NAME
    where_sql, params = _current_batch_filter(request)
    rows = fetch_all(
        f"""
        SELECT COALESCE(acr.decision, 'pending') AS decision, COUNT(*) AS cnt
        FROM address_cleaning_result acr
        JOIN raw_address_record rar
          ON rar.workspace_name = acr.workspace_name
         AND rar.raw_id = acr.raw_id
        WHERE {where_sql}
        GROUP BY COALESCE(acr.decision, 'pending')
        """,
        tuple(params),
    )
    review_reason_rows = fetch_all(
        f"""
        SELECT COALESCE(acr.reason, '') AS reason, COUNT(*) AS cnt
        FROM address_cleaning_result acr
        JOIN raw_address_record rar
          ON rar.workspace_name = acr.workspace_name
         AND rar.raw_id = acr.raw_id
        WHERE {where_sql} AND acr.decision = 'review'
        GROUP BY COALESCE(acr.reason, '')
        ORDER BY COUNT(*) DESC
        LIMIT 10
        """,
        tuple(params),
    )
    review_building_type_rows = fetch_all(
        f"""
        SELECT COALESCE(acr.building_type, 'unknown') AS building_type, COUNT(*) AS cnt
        FROM address_cleaning_result acr
        JOIN raw_address_record rar
          ON rar.workspace_name = acr.workspace_name
         AND rar.raw_id = acr.raw_id
        WHERE {where_sql} AND acr.decision = 'review'
        GROUP BY COALESCE(acr.building_type, 'unknown')
        ORDER BY COUNT(*) DESC
        LIMIT 10
        """,
        tuple(params),
    )
    counts: dict[str, int] = {}
    total = 0
    for row in rows:
        decision = str(row.get("decision") or "pending")
        count = int(row.get("cnt") or 0)
        counts[decision] = count
        total += count
    review_count = counts.get("review", 0)
    accept_count = counts.get("accept", 0)
    enrich_count = counts.get("enrich", 0)
    review_reason_counts = {
        str(row.get("reason") or ""): int(row.get("cnt") or 0)
        for row in review_reason_rows
    }
    review_building_type_counts = {
        str(row.get("building_type") or "unknown"): int(row.get("cnt") or 0)
        for row in review_building_type_rows
    }
    return {
        "status": "success",
        "workspace_name": workspace,
        "source_name": request.source_name,
        "batch_id": request.batch_id,
        "total_rows": total,
        "decision_counts": counts,
        "review_count": review_count,
        "review_rate": round((review_count / total), 4) if total else 0.0,
        "recovered_count": accept_count + enrich_count,
        "recovered_rate": round(((accept_count + enrich_count) / total), 4) if total else 0.0,
        "remaining_review_reason_counts": review_reason_counts,
        "remaining_review_building_type_counts": review_building_type_counts,
    }


@router.post("/reclean-review-opportunities")
async def reclean_review_opportunities(request: CleaningRequest):
    """
    Lists the most review-heavy batches so operators can choose the best reclean target first.
    列出当前 review 最重的批次，帮助运营优先选择最值得重跑的目标批次。
    """
    workspace = request.workspace_name or ADDRESSFORGE_WORKSPACE_NAME
    limit = max(1, min(int(request.preview_limit or 20), 100))
    items = _fetch_review_opportunity_items(workspace, request.source_name, limit)

    return {
        "status": "success",
        "workspace_name": workspace,
        "source_name": request.source_name,
        "limit": limit,
        "items": items,
    }


@router.post("/reclean-top-review-opportunities")
async def reclean_top_review_opportunities(request: CleaningRequest):
    """
    Re-cleans the top review-heavy batches in one safe operation so operators do not
    need to trigger each batch individually.
    按 review 压力自动选择最值得处理的若干批次并统一重清洗，避免运营逐批手动触发。
    """
    from addressforge.core.common import db_cursor

    workspace = request.workspace_name or ADDRESSFORGE_WORKSPACE_NAME
    limit = max(1, min(int(request.opportunity_limit or 3), 20))
    items = _fetch_review_opportunity_items(workspace, request.source_name, limit)
    selected_items = [item for item in items if item.get("source_name") and item.get("batch_id")]
    selected = [
        {"source_name": str(item.get("source_name") or ""), "batch_id": str(item.get("batch_id") or "")}
        for item in selected_items
    ]
    if not selected:
        return {
            "status": "success",
            "workspace_name": workspace,
            "source_name": request.source_name,
            "opportunity_limit": limit,
            "preview_summary": {
                "sampled_rows": 0,
                "decision_counts": {},
                "transition_counts": {},
                "reason_counts": {},
                "projected_recovery_count": 0,
                "projected_remaining_review_count": 0,
                "projected_recovery_rate": 0.0,
                "projected_remaining_review_rate": 0.0,
                "samples": [],
            },
            "processed_batches": [],
            "affected_records": 0,
            "rolled_back_to": None,
            "job": None,
        }

    batch_filters: list[str] = []
    batch_params: list[str] = []
    for item in selected:
        batch_filters.append(
            '(rar.source_name = %s AND JSON_UNQUOTE(JSON_EXTRACT(rar.source_payload, "$.batch_id")) = %s)'
        )
        batch_params.extend([item["source_name"], item["batch_id"]])
    review_where = 'acr.decision = "review" AND acr.workspace_name = %s AND (' + " OR ".join(batch_filters) + ")"
    query_params = [workspace, *batch_params]
    sample_limit = max(1, min(int(request.preview_limit or 100), 500))
    
    # Calculate detailed batch-level preview summaries before actual mutation
    # 在实际变更之前，计算详细的批次级预估摘要
    batch_summaries = _build_batch_recovery_summaries(workspace, selected_items, sample_limit)
    
    # Calculate aggregate preview from batch summaries
    # 从批次摘要计算聚合预估
    total_sampled = sum(int(s.get("sampled_rows") or 0) for s in batch_summaries)
    total_accept = sum(int(s.get("decision_counts", {}).get("accept", 0)) for s in batch_summaries)
    total_enrich = sum(int(s.get("decision_counts", {}).get("enrich", 0)) for s in batch_summaries)
    total_review = sum(int(s.get("decision_counts", {}).get("review", 0)) for s in batch_summaries)
    
    preview_summary = {
        "sampled_rows": total_sampled,
        "decision_counts": {"accept": total_accept, "enrich": total_enrich, "review": total_review},
        "projected_recovery_rate": round((total_accept + total_enrich) / total_sampled, 4) if total_sampled else 0.0,
        "projected_remaining_review_rate": round(total_review / total_sampled, 4) if total_sampled else 0.0,
        "batch_summaries": batch_summaries
    }

    with db_cursor() as (conn, cursor):
        cursor.execute(
            f"""
            SELECT MIN(acr.raw_id) as min_id
            FROM address_cleaning_result acr
            JOIN raw_address_record rar
              ON rar.workspace_name = acr.workspace_name
             AND rar.raw_id = acr.raw_id
            WHERE {review_where}
            """,
            tuple(query_params),
        )
        first_review_row = cursor.fetchone() or {}
        min_id = first_review_row.get("min_id")

        cursor.execute(
            f"""
            UPDATE address_cleaning_result acr
            JOIN raw_address_record rar
              ON rar.workspace_name = acr.workspace_name
             AND rar.raw_id = acr.raw_id
            SET acr.decision = "pending", acr.validation_json = NULL
            WHERE {review_where}
            """,
            tuple(query_params),
        )
        affected = cursor.rowcount

        if min_id:
            cursor.execute(
                'UPDATE control_setting SET setting_value = %s WHERE setting_key = "cleaning.publish.last_raw_id" AND workspace_name = %s',
                (str(min_id - 1), workspace),
            )
        conn.commit()

    job = enqueue_cleaning(workspace, request.batch_size, request.requested_by, "Triggered via Reclean Top Review Opportunities")
    return {
        "status": "success",
        "workspace_name": workspace,
        "source_name": request.source_name,
        "opportunity_limit": limit,
        "preview_summary": preview_summary,
        "processed_batches": selected,
        "affected_records": affected,
        "rolled_back_to": min_id,
        "job": job,
    }


@router.post("/review-residual-buckets")
async def review_residual_buckets(request: CleaningRequest):
    """
    Summarizes the dominant remaining review buckets for the current workspace/source/batch.
    汇总当前工作区/来源/批次下剩余 review 的主桶。
    """
    from addressforge.core.common import fetch_all

    workspace = request.workspace_name or ADDRESSFORGE_WORKSPACE_NAME
    where_sql, params = _current_batch_filter(request)
    limit = max(1, min(int(request.preview_limit or 10), 50))
    review_where = f"{where_sql} AND acr.decision = 'review'"

    reason_rows = fetch_all(
        f"""
        SELECT COALESCE(acr.reason, '') AS reason, COUNT(*) AS cnt
        FROM address_cleaning_result acr
        JOIN raw_address_record rar
          ON rar.workspace_name = acr.workspace_name
         AND rar.raw_id = acr.raw_id
        WHERE {review_where}
        GROUP BY COALESCE(acr.reason, '')
        ORDER BY COUNT(*) DESC
        LIMIT {limit}
        """,
        tuple(params),
    )
    type_rows = fetch_all(
        f"""
        SELECT COALESCE(acr.building_type, 'unknown') AS building_type, COUNT(*) AS cnt
        FROM address_cleaning_result acr
        JOIN raw_address_record rar
          ON rar.workspace_name = acr.workspace_name
         AND rar.raw_id = acr.raw_id
        WHERE {review_where}
        GROUP BY COALESCE(acr.building_type, 'unknown')
        ORDER BY COUNT(*) DESC
        LIMIT {limit}
        """,
        tuple(params),
    )
    disagreement_rows = fetch_all(
        f"""
        SELECT COALESCE(JSON_UNQUOTE(JSON_EXTRACT(acr.validation_json, "$.hints.parser_disagreement_kind")), 'none') AS disagreement_kind,
               COUNT(*) AS cnt
        FROM address_cleaning_result acr
        JOIN raw_address_record rar
          ON rar.workspace_name = acr.workspace_name
         AND rar.raw_id = acr.raw_id
        WHERE {review_where}
        GROUP BY COALESCE(JSON_UNQUOTE(JSON_EXTRACT(acr.validation_json, "$.hints.parser_disagreement_kind")), 'none')
        ORDER BY COUNT(*) DESC
        LIMIT {limit}
        """,
        tuple(params),
    )
    reference_gap_rows = fetch_all(
        f"""
        SELECT COALESCE(JSON_UNQUOTE(JSON_EXTRACT(acr.validation_json, "$.hints.reference_gap_reason")), 'none') AS reference_gap_reason,
               COUNT(*) AS cnt
        FROM address_cleaning_result acr
        JOIN raw_address_record rar
          ON rar.workspace_name = acr.workspace_name
         AND rar.raw_id = acr.raw_id
        WHERE {review_where}
        GROUP BY COALESCE(JSON_UNQUOTE(JSON_EXTRACT(acr.validation_json, "$.hints.reference_gap_reason")), 'none')
        ORDER BY COUNT(*) DESC
        LIMIT {limit}
        """,
        tuple(params),
    )

    return {
        "status": "success",
        "workspace_name": workspace,
        "source_name": request.source_name,
        "batch_id": request.batch_id,
        "limit": limit,
        "reason_counts": {str(row.get("reason") or ""): int(row.get("cnt") or 0) for row in reason_rows},
        "building_type_counts": {str(row.get("building_type") or "unknown"): int(row.get("cnt") or 0) for row in type_rows},
        "parser_disagreement_kind_counts": {
            str(row.get("disagreement_kind") or "none"): int(row.get("cnt") or 0) for row in disagreement_rows
        },
        "reference_gap_reason_counts": {
            str(row.get("reference_gap_reason") or "none"): int(row.get("cnt") or 0) for row in reference_gap_rows
        },
    }

@router.post("/reclean-residual-preview")
async def reclean_residual_preview(request: CleaningRequest):
    """
    Simulates the recovery impact for residual review buckets (History Mismatch, Asset Gap, Location Drift).
    Respects source_name and batch_id filters if provided.
    模拟剩余审核桶（历史不符、资产缺失、位置偏移）的恢复收益。支持按 source_name 和 batch_id 过滤。
    """
    from addressforge.core.common import fetch_all
    workspace = request.workspace_name or ADDRESSFORGE_WORKSPACE_NAME
    sample_limit = max(1, min(int(request.preview_limit or 150), 500))
    
    # Apply current filters (source_name, batch_id)
    # 应用当前过滤器
    filter_sql, filter_params = _current_batch_filter(request)
    
    # 1. Fetch samples for each residual category
    # 1. 获取每个剩余类别的样本
    categories = ["history_mismatch", "asset_gap", "location_drift"]
    total_preview: dict[str, Any] = {
        "sampled_rows": 0,
        "decision_counts": {"accept": 0, "enrich": 0, "review": 0},
        "projected_recovery_rate": 0.0,
        "category_summaries": {}
    }
    
    per_cat_limit = max(1, sample_limit // len(categories))
    
    for cat in categories:
        cat_where = ""
        if cat == "history_mismatch":
            cat_where = "acr.decision = 'review' AND acr.building_type = 'multi_unit'"
        elif cat == "asset_gap":
            cat_where = "acr.decision = 'review' AND acr.building_type = 'multi_unit' AND acr.suggested_unit_number IS NULL"
        elif cat == "location_drift":
            cat_where = "acr.decision = 'review' AND JSON_EXTRACT(acr.validation_json, '$.hints.gps_conflict') = true"
            
        rows = fetch_all(
            f"""
            SELECT acr.raw_id, acr.raw_address_text, rar.city, rar.province, rar.postal_code, rar.country_code
            FROM address_cleaning_result acr
            JOIN raw_address_record rar ON acr.raw_id = rar.raw_id
            WHERE {filter_sql} AND {cat_where}
            ORDER BY acr.confidence ASC, acr.raw_id DESC
            LIMIT %s
            """,
            (*filter_params, per_cat_limit)
        )
        
        if not rows:
            continue
            
        # Run dummy validation for these samples
        preview = _build_targeted_review_preview(workspace, [], per_cat_limit, custom_rows=rows)
        total_preview["sampled_rows"] += preview["sampled_rows"]
        total_preview["decision_counts"]["accept"] += preview.get("decision_counts", {}).get("accept", 0)
        total_preview["decision_counts"]["enrich"] += preview.get("decision_counts", {}).get("enrich", 0)
        total_preview["decision_counts"]["review"] += preview.get("decision_counts", {}).get("review", 0)
        total_preview["category_summaries"][cat] = preview

    if total_preview["sampled_rows"] > 0:
        total_preview["projected_recovery_rate"] = round(
            (total_preview["decision_counts"]["accept"] + total_preview["decision_counts"]["enrich"]) / total_preview["sampled_rows"],
            4
        )

    return {
        "status": "success",
        "workspace_name": workspace,
        "preview": total_preview
    }

@router.post("/reseed-residual-buckets")
async def reseed_residual_buckets(request: CleaningRequest):
    """
    Formal API to trigger active learning re-seeding from residual review buckets.
    Supports scoping by source_name and batch_id.
    用于触发从剩余审核桶进行主动学习重新播种的正式 API。支持按数据源名称和批次 ID 缩小范围。
    """
    from addressforge.learning.gold import seed_active_learning_from_residual_buckets
    workspace = request.workspace_name or ADDRESSFORGE_WORKSPACE_NAME
    
    # Phase 20 Safety Guard: Prevent accidental global re-seeding
    # 第 20 阶段安全守卫：防止意外的全局重新播种
    if not request.source_name and not request.batch_id:
        raise HTTPException(
            status_code=400, 
            detail="Scoping required. Please provide a Source Name or Batch ID to re-seed. / 需要指定范围。请提供数据源名称或批次 ID 以进行重新播种。"
        )

    limit = max(1, min(int(request.preview_limit or 150), 500))
    
    result = seed_active_learning_from_residual_buckets(
        workspace_name=workspace,
        limit=limit,
        target_buckets=request.target_buckets,
        source_name=request.source_name,
        batch_id=request.batch_id
    )
    
    return {
        "status": "success",
        "workspace_name": workspace,
        "source_name": request.source_name,
        "batch_id": request.batch_id,
        **result
    }
