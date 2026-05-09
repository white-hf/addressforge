from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
import re
from typing import Any

from addressforge.core.common import create_run, db_cursor, dumps_payload, fetch_all, finish_run, stable_holdout_bucket
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.core.utils import logger


_APARTMENT_UNIT_HINT_RE = re.compile(
    r"(?:\b(?:APT|APART|SUITE|STE|UNIT|ROOM|RM|FLOOR|FL|BASEMENT|BSMT|LOWER|UPPER|PENTHOUSE|PH|GF|GROUND FLOOR|MAIN FLOOR|MAIN FLR|REAR|FRONT|SIDE)\b|#\s*[A-Z0-9]+)",
    re.IGNORECASE,
)

_STRONG_RESIDENTIAL_UNIT_HINT_RE = re.compile(
    r"(?:\b(?:APT|APARTMENT|UNIT|SUITE|STE|ROOM|RM|FLOOR|FL|BASEMENT|BSMT|PENTHOUSE|PH|REAR|FRONT)\b|#\s*[A-Z0-9]+)",
    re.IGNORECASE,
)

_GEOGRAPHIC_MODIFIER_PLACE_RE = re.compile(
    r"\b(?:UPPER|LOWER)\s+[A-Z][A-Z' -]{2,}\b",
    re.IGNORECASE,
)

_SEMANTIC_AMBIGUITY_RE = re.compile(
    r"(?:\b(?:UPPER|LOWER|BASEMENT|REAR|FRONT|APT|APARTMENT|UNIT|SUITE|STE|ROOM|RM)\b|#\s*[A-Z0-9]+)",
    re.IGNORECASE,
)

_BALANCED_REVIEW_UNIT_HINT_RE = re.compile(
    r"(?:\b(?:APT|APART|APARTMENT|SUITE|STE|UNIT|ROOM|RM|FLOOR|FL|BASEMENT|BSMT|PENTHOUSE|PH|REAR|FRONT|SIDE)\b|#\s*[A-Z0-9]+)",
    re.IGNORECASE,
)

_COMPLETE_SINGLE_UNIT_STREET_RE = re.compile(
    r"\b(?:ST|STREET|AVE|AVENUE|DR|DRIVE|RD|ROAD|LN|LANE|PL|PLACE|CRT|COURT|CRES|CRESCENT|BLVD|BOULEVARD|WAY|TERR|TERRACE|HWY|HIGHWAY|ROUTE|RTE|TRUNK)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GoldLabelRecord:
    gold_label_id: int
    workspace_name: str
    source_name: str
    source_id: str
    task_type: str
    review_status: str
    label_source: str
    score: float | None
    notes: str | None
    label_json: str
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class GoldSnapshotRecord:
    snapshot_id: int
    workspace_name: str
    gold_set_version: str
    split_version: str
    label_source_filter: str
    task_type: str | None
    sample_count: int
    train_count: int
    eval_count: int
    test_count: int
    notes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


def _json_text(value: dict[str, Any] | list[Any] | str | None) -> str:
    if value is None:
        return "{}"
    if isinstance(value, str):
        return value
    return dumps_payload(value if isinstance(value, dict) else {"value": value})


def _existing_reviewed_or_queued_source_ids(
    workspace_name: str,
    source_ids: list[str],
) -> set[str]:
    """
    Returns source_ids that should not be re-queued for human review.
    返回不应再次进入人工审核队列的 source_id 集合。

    Rules:
    - any accepted human gold already exists
    - any active_learning_queue row already exists for that source_id
    """
    cleaned = [str(source_id).strip() for source_id in source_ids if str(source_id).strip()]
    if not cleaned:
        return set()
    placeholders = ", ".join(["%s"] * len(cleaned))
    rows = fetch_all(
        f"""
        SELECT DISTINCT source_id
        FROM gold_label
        WHERE workspace_name = %s
          AND review_status = 'accepted'
          AND label_source = 'human'
          AND source_id IN ({placeholders})
        UNION
        SELECT DISTINCT source_id
        FROM active_learning_queue
        WHERE workspace_name = %s
          AND source_id IN ({placeholders})
        """,
        tuple([workspace_name, *cleaned, workspace_name, *cleaned]),
    )
    return {str(row["source_id"]).strip() for row in rows if row.get("source_id") is not None}


def _looks_like_residential_unit_relabel_candidate(raw_text: str, building_type: str) -> bool:
    text = str(raw_text or "").strip()
    normalized_type = str(building_type or "").strip().lower()
    if normalized_type != "single_unit" or not text:
        return False
    if not _STRONG_RESIDENTIAL_UNIT_HINT_RE.search(text):
        return False
    if _GEOGRAPHIC_MODIFIER_PLACE_RE.search(text) and not re.search(r"\b(?:APT|UNIT|SUITE|STE|ROOM|RM|#)\b", text, re.IGNORECASE):
        return False
    return True


def _looks_like_semantic_ambiguity_candidate(raw_text: str, building_type: str, suggested_unit_number: str | None = None) -> bool:
    text = str(raw_text or "").strip()
    normalized_type = str(building_type or "").strip().lower()
    normalized_unit = str(suggested_unit_number or "").strip().upper()
    if not text or not _SEMANTIC_AMBIGUITY_RE.search(text):
        return False
    if _GEOGRAPHIC_MODIFIER_PLACE_RE.search(text):
        if re.search(r"\b(?:APT|UNIT|SUITE|STE|ROOM|RM|#)\b", text, re.IGNORECASE):
            return True
        return normalized_type == "multi_unit" or bool(normalized_unit)
    if normalized_type == "multi_unit" and bool(normalized_unit) and re.search(r"\b(?:UPPER|LOWER|BASEMENT|REAR|FRONT)\b", text, re.IGNORECASE):
        return True
    if normalized_type == "single_unit" and _STRONG_RESIDENTIAL_UNIT_HINT_RE.search(text):
        return True
    if normalized_type == "multi_unit" and not normalized_unit:
        return True
    return False


def _looks_like_decision_calibration_single_unit_candidate(
    raw_text: str,
    building_type: str,
    decision: str,
    suggested_unit_number: str | None = None,
) -> bool:
    text = str(raw_text or "").strip()
    normalized_type = str(building_type or "").strip().lower()
    normalized_decision = str(decision or "").strip().lower()
    normalized_unit = str(suggested_unit_number or "").strip()
    if normalized_type != "single_unit" or normalized_decision != "review" or normalized_unit:
        return False
    if not text or _BALANCED_REVIEW_UNIT_HINT_RE.search(text):
        return False
    return bool(_COMPLETE_SINGLE_UNIT_STREET_RE.search(text))


def _balanced_review_task_type(pool_name: str, row: dict[str, Any]) -> str:
    normalized_pool = str(pool_name or "").strip().lower()
    raw_text = str(row.get("raw_address_text") or "")
    suggested_unit = str(row.get("suggested_unit_number") or "").strip()
    if normalized_pool == "hard_correction":
        return "building_type"
    if normalized_pool == "unit_boost":
        return "unit_number"
    if normalized_pool == "calibration_multi_unit" and (suggested_unit or _BALANCED_REVIEW_UNIT_HINT_RE.search(raw_text)):
        return "building_type"
    return "review"


def _balanced_review_reason(pool_name: str, base_reason: str | None = None) -> str:
    normalized_pool = str(pool_name or "").strip().lower()
    pool_reason_map = {
        "calibration_single_unit": "balanced calibration: regular single-unit production sample",
        "calibration_multi_unit": "balanced calibration: regular multi-unit production sample",
        "unit_boost": "balanced correction: apartment/unit recall reinforcement sample",
        "hard_correction": "balanced correction: double-number or numbered-road boundary sample",
    }
    summary = pool_reason_map.get(normalized_pool, "balanced review sample")
    extra = str(base_reason or "").strip()
    if extra:
        return f"Balanced pool: {normalized_pool} | {summary} | {extra}"
    return f"Balanced pool: {normalized_pool} | {summary}"


def upsert_gold_label(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    source_name: str = "human",
    source_id: str = "",
    task_type: str = "validation",
    label_json: dict[str, Any] | list[Any] | str | None = None,
    review_status: str = "accepted",
    label_source: str = "human",
    score: float | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    if not source_id:
        raise ValueError("source_id is required")
    payload_text = _json_text(label_json)
    
    # Extract building_type and unit_number for synchronization to result view
    # 提取 building_type 和 unit_number 以同步到结果视图
    import json
    payload_obj = json.loads(payload_text or "{}")
    b_type = payload_obj.get("building_type")
    u_num = payload_obj.get("unit_number")

    with db_cursor() as (conn, cursor):
        # 1. Update/Insert Gold Label (The ML Source)
        # 1. 更新/插入金标 (ML 数据源)
        cursor.execute(
            """
            INSERT INTO gold_label (
                workspace_name, source_name, source_id, task_type, label_json, review_status,
                label_source, score, notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) AS new_row
            ON DUPLICATE KEY UPDATE
                label_json = new_row.label_json,
                review_status = new_row.review_status,
                label_source = new_row.label_source,
                score = new_row.score,
                notes = new_row.notes,
                updated_at = NOW()
            """,
            (workspace_name, source_name, source_id, task_type, payload_text, review_status, label_source, score, notes),
        )
        
        # 2. Sync back to cleaning result view (The UI Source)
        # 2. 同步回清洗结果视图 (UI 展示源)
        if source_name == "address_cleaning_result" or source_name == "human":
            cursor.execute(
                """
                UPDATE address_cleaning_result
                SET building_type = %s,
                    suggested_unit_number = %s,
                    decision = 'accept'
                WHERE raw_id = %s AND workspace_name = %s
                """,
                (b_type, u_num, source_id, workspace_name),
            )
            
        conn.commit()
    row = fetch_all(
        """
        SELECT * FROM gold_label
        WHERE workspace_name = %s AND source_name = %s AND source_id = %s AND task_type = %s
        LIMIT 1
        """,
        (workspace_name, source_name, source_id, task_type),
    )
    return row[0] if row else {}


def list_gold_labels(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    review_status: str | None = None,
    label_source: str | None = None,
    task_type: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM gold_label WHERE workspace_name = %s"
    params: list[Any] = [workspace_name]
    if review_status:
        query += " AND review_status = %s"
        params.append(review_status)
    if label_source:
        query += " AND label_source = %s"
        params.append(label_source)
    if task_type:
        query += " AND task_type = %s"
        params.append(task_type)
    query += " ORDER BY updated_at DESC, gold_label_id DESC LIMIT %s"
    params.append(limit)
    return fetch_all(query, tuple(params))


def count_gold_labels(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    review_status: str | None = None,
    label_source: str | None = None,
) -> int:
    query = "SELECT COUNT(*) AS cnt FROM gold_label WHERE workspace_name = %s"
    params: list[Any] = [workspace_name]
    if review_status:
        query += " AND review_status = %s"
        params.append(review_status)
    if label_source:
        query += " AND label_source = %s"
        params.append(label_source)
    rows = fetch_all(query, tuple(params))
    return int(rows[0]["cnt"]) if rows else 0


def list_gold_snapshots(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    label_source_filter: str | None = None,
    task_type: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM gold_set_snapshot WHERE workspace_name = %s"
    params: list[Any] = [workspace_name]
    if label_source_filter:
        query += " AND label_source_filter = %s"
        params.append(label_source_filter)
    if task_type is not None:
        query += " AND task_type <=> %s"
        params.append(task_type)
    query += " ORDER BY updated_at DESC, snapshot_id DESC LIMIT %s"
    params.append(limit)
    return fetch_all(query, tuple(params))


def freeze_gold_set(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    gold_set_version: str = "gold_v1",
    split_version: str = "v1",
    label_source_filter: str = "human",
    task_type: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    run_id = create_run("ml_gold", notes=f"freeze gold={gold_set_version} split={split_version}")
    try:
        subquery = """
            SELECT source_id, MAX(gold_label_id) AS latest_gold_label_id
            FROM gold_label
            WHERE workspace_name = %s
              AND review_status = 'accepted'
              AND label_source = %s
        """
        subquery_params: list[Any] = [workspace_name, label_source_filter]
        if task_type:
            subquery += " AND task_type = %s"
            subquery_params.append(task_type)
        subquery += " GROUP BY source_id"
        query = f"""
            SELECT g.*
            FROM gold_label g
            JOIN (
                {subquery}
            ) latest
              ON latest.latest_gold_label_id = g.gold_label_id
            WHERE g.workspace_name = %s
            ORDER BY g.gold_label_id ASC
        """
        labels = fetch_all(query, tuple([*subquery_params, workspace_name]))
        sample_count = len(labels)
        assignments: list[tuple[int, str]] = []
        train_count = 0
        eval_count = 0
        test_count = 0
        for row in labels:
            bucket = stable_holdout_bucket(
                workspace_name,
                row.get("source_name"),
                row.get("source_id"),
                row.get("task_type"),
                gold_set_version,
                split_version,
                modulo=100,
            )
            if bucket < 80:
                split_name = "train"
                train_count += 1
            elif bucket < 90:
                split_name = "eval"
                eval_count += 1
            else:
                split_name = "test"
                test_count += 1
            assignments.append((int(row["gold_label_id"]), split_name))

        with db_cursor() as (conn, cursor):
            cursor.execute(
                """
                INSERT INTO gold_set_snapshot (
                    workspace_name, gold_set_version, split_version, label_source_filter,
                    task_type, sample_count, train_count, eval_count, test_count, notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) AS new_row
                ON DUPLICATE KEY UPDATE
                    sample_count = new_row.sample_count,
                    train_count = new_row.train_count,
                    eval_count = new_row.eval_count,
                    test_count = new_row.test_count,
                    notes = new_row.notes,
                    updated_at = NOW()
                """,
                (
                    workspace_name,
                    gold_set_version,
                    split_version,
                    label_source_filter,
                    task_type,
                    sample_count,
                    train_count,
                    eval_count,
                    test_count,
                    notes,
                ),
            )
            conn.commit()

        snapshot_rows = fetch_all(
            """
            SELECT *
            FROM gold_set_snapshot
            WHERE workspace_name = %s
              AND gold_set_version = %s
              AND split_version = %s
              AND label_source_filter = %s
              AND task_type <=> %s
            LIMIT 1
            """,
            (workspace_name, gold_set_version, split_version, label_source_filter, task_type),
        )
        snapshot = snapshot_rows[0] if snapshot_rows else {}
        snapshot_id = int(snapshot.get("snapshot_id") or 0)
        if snapshot_id:
            with db_cursor() as (conn, cursor):
                cursor.execute("DELETE FROM gold_set_member WHERE workspace_name = %s AND snapshot_id = %s", (workspace_name, snapshot_id))
                if assignments:
                    cursor.executemany(
                        """
                        INSERT INTO gold_set_member (
                            workspace_name, snapshot_id, gold_label_id, split_name
                        ) VALUES (%s, %s, %s, %s)
                        """,
                        [(workspace_name, snapshot_id, gold_label_id, split_name) for gold_label_id, split_name in assignments],
                    )
                conn.commit()
        finish_run(
            run_id,
            "completed",
            notes=dumps_payload(
                {
                    "workspace_name": workspace_name,
                    "gold_set_version": gold_set_version,
                    "split_version": split_version,
                    "label_source_filter": label_source_filter,
                    "task_type": task_type,
                    "sample_count": sample_count,
                    "train_count": train_count,
                    "eval_count": eval_count,
                    "test_count": test_count,
                    "snapshot_id": snapshot_id,
                }
            ),
        )
        logger.info(
            "Gold freeze completed: run_id=%s workspace=%s version=%s split=%s samples=%s train=%s eval=%s test=%s",
            run_id,
            workspace_name,
            gold_set_version,
            split_version,
            sample_count,
            train_count,
            eval_count,
            test_count,
        )
        return {
            "run_id": run_id,
            "workspace_name": workspace_name,
            "gold_set_version": gold_set_version,
            "split_version": split_version,
            "label_source_filter": label_source_filter,
            "task_type": task_type,
            "sample_count": sample_count,
            "train_count": train_count,
            "eval_count": eval_count,
            "test_count": test_count,
            "snapshot": snapshot,
        }
    except Exception as exc:
        finish_run(run_id, "failed", notes=dumps_payload({"error": str(exc)}))
        raise


def seed_active_learning_queue(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    limit: int = 250,
    confidence_threshold: float = 0.55,
) -> dict[str, Any]:
    """
    Strategic multi-tiered sampling for human review.
    用于人工审核的战略性多层抽样。
    """
    run_id = create_run("ml_active_learning", notes=f"Strategic v2 limit={limit}")
    logger.info("Starting strategic sampling v2: workspace=%s", workspace_name)
    
    try:
        # Tier Definitions (Strategic Multi-Pool Allocation)
        # 层级定义 (战略性多池分配)
        tiers = [
            # 1. CALIBRATION SINGLE-UNIT (35%): production-like regular houses
            # 1. 单户校准池 (35%): 更接近真实生产分布的常规 house 样本
            {"name": "calibration_single_unit", "ratio": 0.35, "query_type": "calibration_single_unit"},
            # 2. CALIBRATION MULTI-UNIT (15%): production-like regular apartment samples
            # 2. 多单元校准池 (15%): 更接近真实生产分布的常规公寓样本
            {"name": "calibration_multi_unit", "ratio": 0.15, "query_type": "calibration_multi_unit"},
            # 3. UNIT BOOST (30%): focus on apartment/unit recall
            # 3. 单元增强池 (30%): 侧重于提高公寓 unit 召回
            {"name": "unit_boost", "ratio": 0.30, "query_type": "unit_boost"},
            # 4. HARD CORRECTION (20%): double-number and numbered-road boundary samples
            # 4. 硬纠错池 (20%): 双数字和编号道路边界样本
            {"name": "hard_correction", "ratio": 0.20, "query_type": "hard_correction"},
        ]
        
        inserted = 0
        summary_breakdown = {}

        # Exclusion clause: Ensure we don't re-queue processed items
        # 排除条款：确保我们不会重新排队已处理的项目
        exclusion_sql = """
            AND CAST(raw_id AS CHAR) NOT IN (SELECT source_id FROM active_learning_queue WHERE workspace_name = %s)
            AND CAST(raw_id AS CHAR) NOT IN (SELECT source_id FROM gold_label WHERE workspace_name = %s)
        """

        for tier in tiers:
            tier_limit = max(1, int(limit * tier["ratio"]))
            candidates = []
            
            if tier["query_type"] == "calibration_single_unit":
                # High-confidence regular house samples for calibration.
                # 用于校准的高置信常规 house 样本。
                candidates = fetch_all(
                    f"""
                    SELECT raw_id, decision, confidence, reason, building_type, raw_address_text, suggested_unit_number, feature_flags
                    FROM address_cleaning_result
                    WHERE workspace_name = %s
                      AND building_type = 'single_unit'
                      AND decision = 'accept'
                      AND confidence >= 0.88
                      AND (suggested_unit_number IS NULL OR suggested_unit_number = '')
                      AND UPPER(raw_address_text) NOT REGEXP 'APT|APART|APARTMENT|SUITE|STE|UNIT|ROOM|RM|FLOOR|FL|BASEMENT|BSMT|PENTHOUSE|PH|REAR|FRONT|SIDE|#'
                      AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(feature_flags, '$.has_double_number')), '0') <> '1'
                      AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(feature_flags, '$.is_numbered_road')), '0') <> '1'
                    {exclusion_sql}
                    ORDER BY processed_at DESC LIMIT %s
                    """,
                    (workspace_name, workspace_name, workspace_name, tier_limit)
                )
            elif tier["query_type"] == "calibration_multi_unit":
                # High-confidence regular apartment / multi-unit samples for calibration.
                # 用于校准的高置信常规公寓 / 多单元样本。
                candidates = fetch_all(
                    f"""
                    SELECT raw_id, decision, confidence, reason, building_type, raw_address_text, suggested_unit_number, feature_flags
                    FROM address_cleaning_result
                    WHERE workspace_name = %s
                      AND building_type = 'multi_unit'
                      AND decision = 'accept'
                      AND confidence >= 0.80
                      AND (
                            suggested_unit_number IS NOT NULL
                         OR UPPER(raw_address_text) REGEXP 'APT|APART|APARTMENT|SUITE|STE|UNIT|ROOM|RM|FLOOR|FL|BASEMENT|BSMT|PENTHOUSE|PH|REAR|FRONT|SIDE|#'
                      )
                    {exclusion_sql}
                    ORDER BY processed_at DESC LIMIT %s
                    """,
                    (workspace_name, workspace_name, workspace_name, tier_limit)
                )
            elif tier["query_type"] == "unit_boost":
                # Focus on apartment/unit recall improvement.
                # 聚焦公寓 / unit 召回提升。
                candidates = fetch_all(
                    f"""
                    SELECT raw_id, decision, confidence, reason, building_type, raw_address_text, suggested_unit_number, feature_flags
                    FROM address_cleaning_result
                    WHERE workspace_name = %s 
                      AND (
                            building_type = 'multi_unit'
                         OR suggested_unit_number IS NOT NULL
                         OR UPPER(raw_address_text) REGEXP 'APT|APART|APARTMENT|SUITE|STE|UNIT|ROOM|RM|FLOOR|FL|BASEMENT|BSMT|PENTHOUSE|PH|REAR|FRONT|SIDE|#'
                      )
                      AND (decision = 'review' OR confidence <= %s)
                    {exclusion_sql}
                    ORDER BY confidence ASC LIMIT %s
                    """,
                    (workspace_name, confidence_threshold, workspace_name, workspace_name, tier_limit)
                )
            elif tier["query_type"] == "hard_correction":
                # Target false-unit-looking house patterns.
                # 聚焦看起来像 unit 但其实更可能是 house 的边界样本。
                candidates = fetch_all(
                    f"""
                    SELECT raw_id, decision, confidence, reason, building_type, raw_address_text, suggested_unit_number, feature_flags
                    FROM address_cleaning_result
                    WHERE workspace_name = %s 
                      AND (
                            COALESCE(JSON_UNQUOTE(JSON_EXTRACT(feature_flags, '$.has_double_number')), '0') = '1'
                         OR COALESCE(JSON_UNQUOTE(JSON_EXTRACT(feature_flags, '$.is_numbered_road')), '0') = '1'
                      )
                    {exclusion_sql}
                    ORDER BY confidence ASC LIMIT %s
                    """,
                    (workspace_name, workspace_name, workspace_name, tier_limit)
                )

            # Insert candidates into queue
            with db_cursor() as (conn, cursor):
                for row in candidates:
                    source_id = str(row["raw_id"])
                    semantic_task_type = _balanced_review_task_type(tier["name"], row)
                    cursor.execute(
                        """
                        INSERT INTO active_learning_queue (
                            workspace_name, source_name, source_id, task_type, priority, 
                            confidence, reason, status
                        ) VALUES (%s, 'address_cleaning_result', %s, %s, %s, %s, %s, 'queued') AS new_row
                        ON DUPLICATE KEY UPDATE status = 'queued', updated_at = NOW()
                        """,
                        (
                            workspace_name,
                            source_id,
                            semantic_task_type,
                            int(round((1.0 - float(row.get("confidence") or 0.0)) * 100)),
                            row.get("confidence"),
                            _balanced_review_reason(tier["name"], row.get("reason")),
                        ),
                    )
                    inserted += 1
                conn.commit()
            
            summary_breakdown[tier["name"]] = len(candidates)

        finish_run(run_id, "completed", notes=dumps_payload({"inserted": inserted, "breakdown": summary_breakdown}))
        logger.info("Strategic sampling v2 complete. Total: %d, Breakdown: %s", inserted, summary_breakdown)
        
        return {
            "run_id": run_id,
            "inserted": inserted,
            "workspace_name": workspace_name,
            "breakdown": summary_breakdown
        }

    except Exception as exc:
        logger.exception("Strategic sampling v2 failed: %s", exc)
        finish_run(run_id, "failed", notes=str(exc))
        raise


def count_active_learning_queue(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    status: str | None = None,
) -> int:
    query = "SELECT COUNT(*) AS cnt FROM active_learning_queue WHERE workspace_name = %s"
    params: list[Any] = [workspace_name]
    if status:
        query += " AND status = %s"
        params.append(status)
    rows = fetch_all(query, tuple(params))
    return int(rows[0]["cnt"]) if rows else 0


def list_active_learning_queue(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM active_learning_queue WHERE workspace_name = %s"
    params: list[Any] = [workspace_name]
    if status:
        query += " AND status = %s"
        params.append(status)
    query += " ORDER BY priority DESC, created_at DESC, queue_id DESC LIMIT %s"
    params.append(limit)
    return fetch_all(query, tuple(params))


def seed_active_learning_from_errors(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    field: str = "decision",
    limit: int = 100,
) -> dict[str, Any]:
    """
    Directly seeds the review queue using samples from specific error buckets found in evaluations.
    使用评测中发现的特定错误桶样本，直接填充审核队列。
    """
    run_id = create_run("ml_active_learning_from_eval", notes=f"error-driven seed field={field}")
    logger.info("Starting prioritized error-driven seed for field: %s", field)
    
    try:
        # 1. Fetch latest evaluation with bucket statistics
        # 1. 获取带有桶统计信息的最新评测
        recent_eval = fetch_all(
            """
            SELECT metrics_json 
            FROM model_registry 
            WHERE workspace_name = %s AND status = 'evaluated'
            ORDER BY created_at DESC LIMIT 1
            """,
            (workspace_name,)
        )
        
        if not recent_eval:
            return {"inserted": 0, "reason": "no_evaluation_found"}
            
        metrics = json.loads(recent_eval[0]["metrics_json"] or "{}")
        error_key = f"{field}_errors"
        error_samples = metrics.get(error_key, [])
        
        if not error_samples:
            return {"inserted": 0, "reason": "no_errors_in_eval"}

        # 2. Sort samples by error-bucket severity (Heuristic: patterns with low global confidence first)
        # 2. 按错误桶严重程度排序 (启发式：低全局置信度的模式优先)
        # In a real setup, we would group by 'bucket' and count frequency here.
        # 在真实设置中，我们会按“桶”分组并在此计算频率。
        sorted_samples = sorted(error_samples, key=lambda x: x.get("confidence", 1.0))

        # 3. Batch upsert into review queue with top priority (100)
        # 3. 以最高优先级 (100) 批量插入/更新审核队列
        inserted = 0
        existing_source_ids = _existing_reviewed_or_queued_source_ids(
            workspace_name,
            [str(sample.get("source_id") or "") for sample in sorted_samples[:limit]],
        )
        with db_cursor() as (conn, cursor):
            for s in sorted_samples[:limit]:
                source_id = str(s.get("source_id") or "").strip()
                if not source_id or source_id in existing_source_ids:
                    continue
                cursor.execute(
                    """
                    INSERT INTO active_learning_queue (
                        workspace_name, source_name, source_id, task_type, priority, status, reason
                    ) VALUES (%s, 'evaluation_error', %s, %s, 100, 'queued', %s) AS new_row
                    ON DUPLICATE KEY UPDATE
                        priority = 100,
                        status = 'queued',
                        reason = new_row.reason,
                        updated_at = NOW()
                    """,
                    (workspace_name, source_id, field, f"Priority error bucket: {field}")
                )
                inserted += 1
            conn.commit()
            
        finish_run(run_id, "completed", notes=dumps_payload({"inserted": inserted, "field": field}))
        logger.info("Prioritized seeding completed: %d samples from error buckets.", inserted)
        return {"inserted": inserted}

        
    except Exception as exc:
        logger.exception("Error-driven seeding failed: %s", exc)
        finish_run(run_id, "failed", notes=dumps_payload({"error": str(exc)}))
        raise


def seed_unit_commercial_review_queue(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    limit: int = 150,
    confidence_threshold: float = 0.80,
) -> dict[str, Any]:
    """
    Seeds a targeted review queue for unit-bearing and commercial-like Canada samples.
    为带 unit 和商业类加拿大地址样本生成定向审核队列。
    """
    run_id = create_run("ml_active_learning", notes=f"targeted unit/commercial seed threshold={confidence_threshold}")
    try:
        candidates = fetch_all(
            """
            SELECT raw_id, decision, confidence, reason, building_type, raw_address_text, suggested_unit_number
            FROM address_cleaning_result
            WHERE workspace_name = %s
              AND (
                    building_type IN ('commercial', 'multi_unit')
                 OR suggested_unit_number IS NOT NULL
                 OR UPPER(raw_address_text) REGEXP 'APT|APART|SUITE|STE|UNIT|#|ROOM|RM|FLOOR|FL|BASEMENT|BSMT|LOWER|UPPER|PENTHOUSE|PH|GF|GROUND FLOOR|MAIN FLOOR|MAIN FLR|REAR|FRONT|SIDE|MALL|PLAZA|SQUARE|TOWER|OFFICE|CENTRE|CENTER'
              )
              AND (confidence <= %s OR decision = 'review')
            ORDER BY
                CASE
                    WHEN building_type = 'commercial' THEN 0
                    WHEN building_type = 'multi_unit' THEN 1
                    WHEN suggested_unit_number IS NOT NULL THEN 2
                    ELSE 3
                END ASC,
                confidence ASC,
                raw_id DESC
            LIMIT %s
            """,
            (workspace_name, confidence_threshold, limit),
        )
        inserted = 0
        existing_source_ids = _existing_reviewed_or_queued_source_ids(
            workspace_name,
            [str(row["raw_id"]) for row in candidates],
        )
        with db_cursor() as (conn, cursor):
            for row in candidates:
                source_id = str(row["raw_id"])
                if source_id in existing_source_ids:
                    continue
                btype = str(row.get("building_type") or "validation")
                reason = row.get("reason") or "Targeted unit/commercial review sample"
                priority = 95 if btype == "commercial" else 90 if btype == "multi_unit" else 85
                cursor.execute(
                    """
                    INSERT INTO active_learning_queue (
                        workspace_name, source_name, source_id, task_type, priority, confidence, reason, status
                    ) VALUES (%s, 'address_cleaning_result', %s, %s, %s, %s, %s, 'queued') AS new_row
                    ON DUPLICATE KEY UPDATE
                        priority = new_row.priority,
                        confidence = new_row.confidence,
                        reason = new_row.reason,
                        status = 'queued',
                        updated_at = NOW()
                    """,
                    (
                        workspace_name,
                        source_id,
                        btype if btype in {"commercial", "multi_unit", "single_unit"} else "building_type",
                        priority,
                        row.get("confidence"),
                        reason,
                    ),
                )
                inserted += 1
            conn.commit()
        finish_run(run_id, "completed", notes=dumps_payload({"inserted": inserted, "limit": limit}))
        return {
            "run_id": run_id,
            "workspace_name": workspace_name,
            "inserted": inserted,
            "candidates_found": len(candidates),
        }
    except Exception as exc:
        logger.exception("Targeted unit/commercial seeding failed: %s", exc)
        finish_run(run_id, "failed", notes=dumps_payload({"error": str(exc)}))
        raise


def seed_apartment_unit_hard_samples(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    limit: int = 150,
    confidence_threshold: float = 0.84,
) -> dict[str, Any]:
    """
    Seeds a review queue focused on apartment/unit hard cases.
    为公寓 / unit 高价值难样本生成定向审核队列。
    """
    run_id = create_run("ml_active_learning", notes=f"apartment/unit hard sample seed threshold={confidence_threshold}")
    try:
        queue_entries: list[dict[str, Any]] = []

        recent_eval = fetch_all(
            """
            SELECT metrics_json
            FROM model_registry
            WHERE workspace_name = %s AND status = 'evaluated'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (workspace_name,),
        )
        if recent_eval:
            try:
                metrics = json.loads(recent_eval[0].get("metrics_json") or "{}")
            except Exception:
                metrics = {}
            unit_errors = metrics.get("unit_number_errors") or []
            building_errors = metrics.get("building_type_errors") or []
            for sample in unit_errors[:limit]:
                source_id = str(sample.get("source_id") or "").strip()
                if not source_id:
                    continue
                queue_entries.append(
                    {
                        "source_name": "evaluation_error",
                        "source_id": source_id,
                        "task_type": "unit_number",
                        "priority": 100,
                        "confidence": None,
                        "reason": f"Apartment/unit hard sample from evaluation: {sample.get('bucket') or 'UNIT_ERROR'}",
                    }
                )
            for sample in building_errors[: limit // 2]:
                source_id = str(sample.get("source_id") or "").strip()
                raw_text = str(sample.get("raw_text") or "")
                if not source_id or not _APARTMENT_UNIT_HINT_RE.search(raw_text):
                    continue
                queue_entries.append(
                    {
                        "source_name": "evaluation_error",
                        "source_id": source_id,
                        "task_type": "building_type",
                        "priority": 96,
                        "confidence": None,
                        "reason": f"Apartment/unit building-type hard sample: {sample.get('bucket') or 'BUILDING_ERROR'}",
                    }
                )

        llm_rows = fetch_all(
            """
            SELECT
                q.source_id,
                q.confidence,
                q.reason,
                acr.raw_address_text,
                acr.building_type,
                acr.suggested_unit_number,
                rpc.llm_json
            FROM active_learning_queue q
            JOIN address_cleaning_result acr
              ON acr.workspace_name = q.workspace_name
             AND CAST(acr.raw_id AS CHAR) = q.source_id
            JOIN review_prescreen_cache rpc
              ON rpc.workspace_name = q.workspace_name
             AND rpc.source_name = q.source_name
             AND rpc.source_id = q.source_id
             AND rpc.task_type = q.task_type
            WHERE q.workspace_name = %s
            ORDER BY q.updated_at DESC
            LIMIT %s
            """,
            (workspace_name, max(limit * 2, 200)),
        )
        for row in llm_rows:
            raw_text = str(row.get("raw_address_text") or "")
            if not _APARTMENT_UNIT_HINT_RE.search(raw_text):
                continue
            try:
                llm_json = row.get("llm_json")
                if isinstance(llm_json, str):
                    llm_json = json.loads(llm_json)
            except Exception:
                llm_json = {}
            if not isinstance(llm_json, dict):
                continue
            system_building = str(row.get("building_type") or "").strip().lower()
            system_unit = str(row.get("suggested_unit_number") or "").strip().upper()
            llm_building = str(llm_json.get("building_type") or "").strip().lower()
            llm_unit = str(llm_json.get("unit_number") or "").strip().upper()
            if llm_building == system_building and llm_unit == system_unit:
                continue
            source_id = str(row.get("source_id") or "").strip()
            if not source_id:
                continue
            queue_entries.append(
                {
                    "source_name": "llm_disagreement",
                    "source_id": source_id,
                    "task_type": "unit_number" if llm_unit != system_unit else "building_type",
                    "priority": 94,
                    "confidence": row.get("confidence"),
                    "reason": "Apartment/unit hard sample from LLM disagreement",
                }
            )

        candidate_rows = fetch_all(
            """
            SELECT raw_id, confidence, reason, raw_address_text, building_type, suggested_unit_number, decision
            FROM address_cleaning_result
            WHERE workspace_name = %s
              AND (
                    UPPER(raw_address_text) REGEXP 'APT|APART|SUITE|STE|UNIT|ROOM|RM|FLOOR|FL|BASEMENT|BSMT|LOWER|UPPER|PENTHOUSE|PH|GF|GROUND FLOOR|MAIN FLOOR|MAIN FLR|REAR|FRONT|SIDE|#'
                 OR building_type = 'multi_unit'
              )
              AND (
                    suggested_unit_number IS NULL
                 OR decision = 'review'
                 OR confidence <= %s
                 OR building_type = 'single_unit'
              )
            ORDER BY
                CASE
                    WHEN suggested_unit_number IS NULL THEN 0
                    WHEN decision = 'review' THEN 1
                    WHEN building_type = 'single_unit' THEN 2
                    ELSE 3
                END ASC,
                confidence ASC,
                raw_id DESC
            LIMIT %s
            """,
            (workspace_name, confidence_threshold, max(limit * 2, 200)),
        )
        for row in candidate_rows:
            source_id = str(row.get("raw_id") or "").strip()
            raw_text = str(row.get("raw_address_text") or "")
            if not source_id or not _APARTMENT_UNIT_HINT_RE.search(raw_text):
                continue
            queue_entries.append(
                {
                    "source_name": "address_cleaning_result",
                    "source_id": source_id,
                    "task_type": "unit_number" if not row.get("suggested_unit_number") else "building_type",
                    "priority": 90,
                    "confidence": row.get("confidence"),
                    "reason": row.get("reason") or "Apartment/unit hard sample from candidate pool",
                }
            )

        deduped: list[dict[str, Any]] = []
        seen_source_ids: set[str] = set()
        for entry in sorted(queue_entries, key=lambda item: (-int(item["priority"]), str(item["source_id"]))):
            source_id = str(entry["source_id"])
            if source_id in seen_source_ids:
                continue
            seen_source_ids.add(source_id)
            deduped.append(entry)
            if len(deduped) >= limit:
                break

        existing_source_ids = _existing_reviewed_or_queued_source_ids(
            workspace_name,
            [str(item["source_id"]) for item in deduped],
        )
        inserted = 0
        with db_cursor() as (conn, cursor):
            for item in deduped:
                source_id = str(item["source_id"])
                if source_id in existing_source_ids:
                    continue
                cursor.execute(
                    """
                    INSERT INTO active_learning_queue (
                        workspace_name, source_name, source_id, task_type, priority, confidence, reason, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued') AS new_row
                    ON DUPLICATE KEY UPDATE
                        priority = new_row.priority,
                        confidence = new_row.confidence,
                        reason = new_row.reason,
                        status = 'queued',
                        updated_at = NOW()
                    """,
                    (
                        workspace_name,
                        str(item["source_name"]),
                        source_id,
                        str(item["task_type"]),
                        int(item["priority"]),
                        item.get("confidence"),
                        str(item["reason"]),
                    ),
                )
                inserted += 1
            conn.commit()
        finish_run(
            run_id,
            "completed",
            notes=dumps_payload(
                {
                    "inserted": inserted,
                    "candidates_found": len(queue_entries),
                    "deduped_candidates": len(deduped),
                    "limit": limit,
                }
            ),
        )
        return {
            "run_id": run_id,
            "workspace_name": workspace_name,
            "inserted": inserted,
            "candidates_found": len(queue_entries),
            "deduped_candidates": len(deduped),
        }
    except Exception as exc:
        logger.exception("Apartment/unit hard-sample seeding failed: %s", exc)
        finish_run(run_id, "failed", notes=dumps_payload({"error": str(exc)}))
        raise


def seed_label_consistency_relabel_queue(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Seeds a relabel review batch for likely building_type label inconsistencies.
    为疑似 building_type 标注不一致样本生成复审队列。
    """
    run_id = create_run("ml_active_learning", notes="label consistency relabel batch")
    try:
        rows = fetch_all(
            """
            SELECT
                g.source_id,
                g.task_type,
                g.label_json,
                r.raw_address_text
            FROM gold_label g
            JOIN (
                SELECT source_id, MAX(gold_label_id) AS latest_gold_label_id
                FROM gold_label
                WHERE workspace_name = %s
                  AND review_status = 'accepted'
                  AND label_source = 'human'
                GROUP BY source_id
            ) latest
              ON latest.latest_gold_label_id = g.gold_label_id
            JOIN raw_address_record r
              ON r.workspace_name = g.workspace_name
             AND CAST(r.raw_id AS CHAR) = g.source_id
            WHERE g.workspace_name = %s
            ORDER BY g.updated_at DESC, g.gold_label_id DESC
            """,
            (workspace_name, workspace_name),
        )

        candidates: list[dict[str, Any]] = []
        for row in rows:
            try:
                label_json = row.get("label_json")
                label = json.loads(label_json or "{}") if isinstance(label_json, str) else (label_json or {})
            except Exception:
                label = {}
            building_type = str(label.get("building_type") or label.get("structure_type") or "").strip().lower()
            raw_text = str(row.get("raw_address_text") or "")
            if not _looks_like_residential_unit_relabel_candidate(raw_text, building_type):
                continue
            candidates.append(
                {
                    "source_name": "gold_relabel",
                    "source_id": str(row["source_id"]),
                    "task_type": "building_type",
                    "priority": 99,
                    "confidence": None,
                    "reason": "Relabel review: strong apartment/unit hint but current human gold is single_unit",
                    "raw_address_text": raw_text,
                }
            )

        deduped: list[dict[str, Any]] = []
        seen_source_ids: set[str] = set()
        for item in candidates:
            source_id = str(item["source_id"]).strip()
            if not source_id or source_id in seen_source_ids:
                continue
            seen_source_ids.add(source_id)
            deduped.append(item)
            if len(deduped) >= limit:
                break

        inserted = 0
        with db_cursor() as (conn, cursor):
            for item in deduped:
                cursor.execute(
                    """
                    INSERT INTO active_learning_queue (
                        workspace_name, source_name, source_id, task_type, priority, confidence, reason, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued') AS new_row
                    ON DUPLICATE KEY UPDATE
                        priority = new_row.priority,
                        confidence = new_row.confidence,
                        reason = new_row.reason,
                        status = 'queued',
                        updated_at = NOW()
                    """,
                    (
                        workspace_name,
                        str(item["source_name"]),
                        str(item["source_id"]),
                        str(item["task_type"]),
                        int(item["priority"]),
                        item.get("confidence"),
                        str(item["reason"]),
                    ),
                )
                inserted += 1
            conn.commit()

        finish_run(
            run_id,
            "completed",
            notes=dumps_payload(
                {
                    "inserted": inserted,
                    "candidates_found": len(candidates),
                    "deduped_candidates": len(deduped),
                    "limit": limit,
                }
            ),
        )
        return {
            "run_id": run_id,
            "workspace_name": workspace_name,
            "inserted": inserted,
            "candidates_found": len(candidates),
            "deduped_candidates": len(deduped),
        }
    except Exception as exc:
        logger.exception("Label consistency relabel seeding failed: %s", exc)
        finish_run(run_id, "failed", notes=dumps_payload({"error": str(exc)}))
        raise


def seed_semantic_disambiguation_review_queue(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    limit: int = 100,
    confidence_threshold: float = 0.88,
) -> dict[str, Any]:
    """
    Seeds a dedicated review batch for semantic ambiguity cases such as
    geographic Upper/Lower vs residential sub-unit signals.
    为地名 Upper/Lower 与住宅 sub-unit 信号冲突等语义歧义样本生成专门复审批次。
    """
    run_id = create_run("ml_active_learning", notes=f"semantic ambiguity relabel batch threshold={confidence_threshold}")
    try:
        candidates: list[dict[str, Any]] = []

        recent_eval = fetch_all(
            """
            SELECT metrics_json
            FROM model_registry
            WHERE workspace_name = %s AND status = 'evaluated'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (workspace_name,),
        )
        if recent_eval:
            try:
                metrics = json.loads(recent_eval[0].get("metrics_json") or "{}")
            except Exception:
                metrics = {}
            for sample in metrics.get("building_type_errors") or []:
                source_id = str(sample.get("source_id") or "").strip()
                raw_text = str(sample.get("raw_text") or "")
                predicted = str(sample.get("predicted") or "")
                if not source_id or not _looks_like_semantic_ambiguity_candidate(raw_text, predicted, None):
                    continue
                candidates.append(
                    {
                        "source_name": "semantic_disambiguation_eval",
                        "source_id": source_id,
                        "task_type": "building_type",
                        "priority": 100,
                        "confidence": None,
                        "reason": f"Semantic ambiguity from evaluation bucket: {sample.get('bucket') or 'BUILDING_TYPE_ERROR'}",
                        "raw_address_text": raw_text,
                    }
                )

        rows = fetch_all(
            """
            SELECT
                acr.raw_id,
                acr.building_type,
                acr.suggested_unit_number,
                acr.confidence,
                acr.reason,
                acr.decision,
                acr.raw_address_text
            FROM address_cleaning_result acr
            WHERE acr.workspace_name = %s
              AND (
                    acr.decision = 'review'
                 OR acr.confidence <= %s
                 OR acr.building_type IN ('single_unit', 'multi_unit')
              )
            ORDER BY acr.confidence ASC, acr.raw_id DESC
            LIMIT %s
            """,
            (workspace_name, confidence_threshold, max(limit * 8, 800)),
        )

        for row in rows:
            raw_text = str(row.get("raw_address_text") or "")
            building_type = str(row.get("building_type") or "")
            suggested_unit_number = row.get("suggested_unit_number")
            if not _looks_like_semantic_ambiguity_candidate(raw_text, building_type, suggested_unit_number):
                continue
            source_id = str(row.get("raw_id") or "").strip()
            if not source_id:
                continue
            priority = 97 if _GEOGRAPHIC_MODIFIER_PLACE_RE.search(raw_text) else 95
            if str(row.get("decision") or "").strip().lower() == "review":
                priority += 1
            candidates.append(
                {
                    "source_name": "semantic_disambiguation",
                    "source_id": source_id,
                    "task_type": "building_type",
                    "priority": priority,
                    "confidence": row.get("confidence"),
                    "reason": row.get("reason") or "Semantic ambiguity review: unit-like token vs geographic modifier",
                    "raw_address_text": raw_text,
                }
            )

        deduped: list[dict[str, Any]] = []
        seen_source_ids: set[str] = set()
        for item in candidates:
            source_id = str(item["source_id"]).strip()
            if not source_id or source_id in seen_source_ids:
                continue
            seen_source_ids.add(source_id)
            deduped.append(item)
            if len(deduped) >= limit:
                break

        existing_source_ids = _existing_reviewed_or_queued_source_ids(
            workspace_name,
            [str(item["source_id"]) for item in deduped],
        )
        inserted = 0
        with db_cursor() as (conn, cursor):
            for item in deduped:
                source_id = str(item["source_id"])
                if source_id in existing_source_ids:
                    continue
                cursor.execute(
                    """
                    INSERT INTO active_learning_queue (
                        workspace_name, source_name, source_id, task_type, priority, confidence, reason, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued') AS new_row
                    ON DUPLICATE KEY UPDATE
                        priority = new_row.priority,
                        confidence = new_row.confidence,
                        reason = new_row.reason,
                        status = 'queued',
                        updated_at = NOW()
                    """,
                    (
                        workspace_name,
                        str(item["source_name"]),
                        source_id,
                        str(item["task_type"]),
                        int(item["priority"]),
                        item.get("confidence"),
                        str(item["reason"]),
                    ),
                )
                inserted += 1
            conn.commit()

        finish_run(
            run_id,
            "completed",
            notes=dumps_payload(
                {
                    "inserted": inserted,
                    "candidates_found": len(candidates),
                    "deduped_candidates": len(deduped),
                    "limit": limit,
                    "confidence_threshold": confidence_threshold,
                }
            ),
        )
        return {
            "run_id": run_id,
            "workspace_name": workspace_name,
            "inserted": inserted,
            "candidates_found": len(candidates),
            "deduped_candidates": len(deduped),
            "confidence_threshold": confidence_threshold,
        }
    except Exception as exc:
        logger.exception("Semantic ambiguity review seeding failed: %s", exc)
        finish_run(run_id, "failed", notes=dumps_payload({"error": str(exc)}))
        raise


def seed_decision_calibration_review_queue(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    limit: int = 80,
    confidence_threshold: float = 0.66,
) -> dict[str, Any]:
    """
    Seeds a dedicated review batch for historical review cases that now look
    like clean single-unit accepts but are still likely to be labeled as review.
    为历史 review 但当前看起来更像 clean single-unit accept 的样本生成专门的 decision 校准复审核批次。
    """
    run_id = create_run("ml_active_learning", notes=f"decision calibration batch threshold={confidence_threshold}")
    try:
        candidates: list[dict[str, Any]] = []

        recent_eval = fetch_all(
            """
            SELECT metrics_json
            FROM model_registry
            WHERE workspace_name = %s AND status = 'evaluated'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (workspace_name,),
        )
        if recent_eval:
            try:
                metrics = json.loads(recent_eval[0].get("metrics_json") or "{}")
            except Exception:
                metrics = {}
            for sample in metrics.get("decision_errors") or []:
                bucket = str(sample.get("bucket") or "").strip().upper()
                predicted = str(sample.get("predicted") or "").strip().lower()
                raw_text = str(sample.get("raw_text") or "")
                building_type = str(sample.get("building_type") or "")
                source_id = str(sample.get("source_id") or "").strip()
                if (
                    bucket != "OVER_SENSITIVE_REVIEW"
                    or predicted != "review"
                    or not source_id
                    or not _looks_like_decision_calibration_single_unit_candidate(raw_text, building_type, predicted, None)
                ):
                    continue
                candidates.append(
                    {
                        "source_name": "decision_calibration_eval",
                        "source_id": source_id,
                        "task_type": "review",
                        "priority": 99,
                        "confidence": None,
                        "reason": "Decision calibration from evaluation: single-unit review likely should be accept",
                        "raw_address_text": raw_text,
                    }
                )

        rows = fetch_all(
            """
            SELECT
                acr.raw_id,
                acr.decision,
                acr.confidence,
                acr.reason,
                acr.building_type,
                acr.raw_address_text,
                acr.suggested_unit_number
            FROM address_cleaning_result acr
            WHERE acr.workspace_name = %s
              AND acr.decision = 'review'
              AND acr.building_type = 'single_unit'
              AND acr.confidence >= %s
              AND (acr.suggested_unit_number IS NULL OR acr.suggested_unit_number = '')
            ORDER BY acr.confidence DESC, acr.raw_id DESC
            LIMIT %s
            """,
            (workspace_name, confidence_threshold, max(limit * 8, 640)),
        )

        for row in rows:
            raw_text = str(row.get("raw_address_text") or "")
            if not _looks_like_decision_calibration_single_unit_candidate(
                raw_text,
                str(row.get("building_type") or ""),
                str(row.get("decision") or ""),
                row.get("suggested_unit_number"),
            ):
                continue
            source_id = str(row.get("raw_id") or "").strip()
            if not source_id:
                continue
            candidates.append(
                {
                    "source_name": "decision_calibration",
                    "source_id": source_id,
                    "task_type": "review",
                    "priority": 96,
                    "confidence": row.get("confidence"),
                    "reason": row.get("reason") or "Decision calibration review: single-unit review likely should be accept",
                    "raw_address_text": raw_text,
                }
            )

        deduped: list[dict[str, Any]] = []
        seen_source_ids: set[str] = set()
        for item in candidates:
            source_id = str(item["source_id"]).strip()
            if not source_id or source_id in seen_source_ids:
                continue
            seen_source_ids.add(source_id)
            deduped.append(item)
            if len(deduped) >= limit:
                break

        existing_source_ids = _existing_reviewed_or_queued_source_ids(
            workspace_name,
            [str(item["source_id"]) for item in deduped],
        )
        inserted = 0
        with db_cursor() as (conn, cursor):
            for item in deduped:
                source_id = str(item["source_id"])
                if source_id in existing_source_ids:
                    continue
                cursor.execute(
                    """
                    INSERT INTO active_learning_queue (
                        workspace_name, source_name, source_id, task_type, priority, confidence, reason, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued') AS new_row
                    ON DUPLICATE KEY UPDATE
                        priority = new_row.priority,
                        confidence = new_row.confidence,
                        reason = new_row.reason,
                        status = 'queued',
                        updated_at = NOW()
                    """,
                    (
                        workspace_name,
                        str(item["source_name"]),
                        source_id,
                        str(item["task_type"]),
                        int(item["priority"]),
                        item.get("confidence"),
                        str(item["reason"]),
                    ),
                )
                inserted += 1
            conn.commit()

        finish_run(
            run_id,
            "completed",
            notes=dumps_payload(
                {
                    "inserted": inserted,
                    "candidates_found": len(candidates),
                    "deduped_candidates": len(deduped),
                    "limit": limit,
                    "confidence_threshold": confidence_threshold,
                }
            ),
        )
        return {
            "run_id": run_id,
            "inserted": inserted,
            "candidates_found": len(candidates),
            "deduped_candidates": len(deduped),
            "limit": limit,
            "confidence_threshold": confidence_threshold,
            "workspace_name": workspace_name,
        }
    except Exception as exc:
        logger.exception("Decision calibration review seeding failed: %s", exc)
        finish_run(run_id, "failed", notes=dumps_payload({"error": str(exc)}))
        raise


def seed_decision_minority_label_review_queue(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    limit: int = 80,
    confidence_threshold: float = 0.72,
) -> dict[str, Any]:
    """
    Seeds a dedicated review batch to increase rare `review/reject` decision labels.
    为稀缺的 `review/reject` decision 标签生成专门审核批次。
    """
    run_id = create_run("ml_active_learning", notes=f"decision minority label batch threshold={confidence_threshold}")
    try:
        candidates: list[dict[str, Any]] = []
        bucket_queries = [
            (
                "decision_reject_candidate",
                99,
                """
                SELECT raw_id, decision, confidence, reason, building_type, raw_address_text, suggested_unit_number
                FROM address_cleaning_result
                WHERE workspace_name = %s
                  AND decision = 'reject'
                ORDER BY confidence ASC, raw_id DESC
                LIMIT %s
                """,
                (workspace_name, max(limit * 4, 160)),
            ),
            (
                "decision_review_incomplete",
                98,
                """
                SELECT raw_id, decision, confidence, reason, building_type, raw_address_text, suggested_unit_number
                FROM address_cleaning_result
                WHERE workspace_name = %s
                  AND decision = 'review'
                  AND reason = 'Address is incomplete and needs manual confirmation.'
                ORDER BY confidence ASC, raw_id DESC
                LIMIT %s
                """,
                (workspace_name, max(limit * 4, 160)),
            ),
            (
                "decision_review_commercial",
                97,
                """
                SELECT raw_id, decision, confidence, reason, building_type, raw_address_text, suggested_unit_number
                FROM address_cleaning_result
                WHERE workspace_name = %s
                  AND decision = 'review'
                  AND reason = 'Commercial-looking address parsed well, but unit details may need confirmation.'
                ORDER BY confidence ASC, raw_id DESC
                LIMIT %s
                """,
                (workspace_name, max(limit * 3, 120)),
            ),
            (
                "decision_review_low_confidence",
                96,
                """
                SELECT raw_id, decision, confidence, reason, building_type, raw_address_text, suggested_unit_number
                FROM address_cleaning_result
                WHERE workspace_name = %s
                  AND decision = 'review'
                  AND reason = 'Parser confidence is low; review is safer than rejection.'
                ORDER BY confidence ASC, raw_id DESC
                LIMIT %s
                """,
                (workspace_name, max(limit * 3, 120)),
            ),
            (
                "decision_review_moderate",
                95,
                """
                SELECT raw_id, decision, confidence, reason, building_type, raw_address_text, suggested_unit_number
                FROM address_cleaning_result
                WHERE workspace_name = %s
                  AND decision = 'review'
                  AND reason = 'Parser confidence is moderate; review is safer.'
                  AND confidence <= %s
                ORDER BY confidence ASC, raw_id DESC
                LIMIT %s
                """,
                (workspace_name, confidence_threshold, max(limit * 3, 120)),
            ),
        ]

        bucketed_candidates: dict[str, list[dict[str, Any]]] = {}
        for bucket, priority, query, params in bucket_queries:
            rows = fetch_all(query, params)
            prepared: list[dict[str, Any]] = []
            for row in rows:
                source_id = str(row.get("raw_id") or "").strip()
                if not source_id:
                    continue
                reason = str(row.get("reason") or "").strip()
                prepared.append(
                    {
                        "source_name": "decision_minority_label",
                        "source_id": source_id,
                        "task_type": "review",
                        "priority": priority,
                        "confidence": row.get("confidence"),
                        "reason": f"Decision minority label seeding [{bucket}]: {reason or 'review/reject label enrichment candidate'}",
                        "bucket": bucket,
                    }
                )
            bucketed_candidates[bucket] = prepared
            candidates.extend(prepared)

        bucket_counts: dict[str, int] = {bucket: len(items) for bucket, items in bucketed_candidates.items() if items}
        all_candidate_source_ids = [str(item["source_id"]) for item in candidates if str(item.get("source_id") or "").strip()]
        existing_source_ids = _existing_reviewed_or_queued_source_ids(
            workspace_name,
            all_candidate_source_ids,
        )

        deduped: list[dict[str, Any]] = []
        seen_source_ids: set[str] = set()
        ordered_buckets = [bucket for bucket, _priority, _query, _params in bucket_queries]
        bucket_positions: dict[str, int] = {bucket: 0 for bucket in ordered_buckets}
        while len(deduped) < limit:
            made_progress = False
            for bucket in ordered_buckets:
                items = bucketed_candidates.get(bucket) or []
                position = bucket_positions[bucket]
                while position < len(items):
                    item = items[position]
                    position += 1
                    source_id = str(item["source_id"]).strip()
                    if not source_id or source_id in seen_source_ids or source_id in existing_source_ids:
                        continue
                    seen_source_ids.add(source_id)
                    deduped.append(item)
                    made_progress = True
                    break
                bucket_positions[bucket] = position
                if len(deduped) >= limit:
                    break
            if not made_progress:
                break

        inserted = 0
        inserted_bucket_counts: dict[str, int] = {}
        with db_cursor() as (conn, cursor):
            for item in deduped:
                source_id = str(item["source_id"])
                cursor.execute(
                    """
                    INSERT INTO active_learning_queue (
                        workspace_name, source_name, source_id, task_type, priority, confidence, reason, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued') AS new_row
                    ON DUPLICATE KEY UPDATE
                        priority = new_row.priority,
                        confidence = new_row.confidence,
                        reason = new_row.reason,
                        status = 'queued',
                        updated_at = NOW()
                    """,
                    (
                        workspace_name,
                        str(item["source_name"]),
                        source_id,
                        str(item["task_type"]),
                        int(item["priority"]),
                        item.get("confidence"),
                        str(item["reason"]),
                    ),
                )
                inserted += 1
                bucket = str(item.get("bucket") or "")
                inserted_bucket_counts[bucket] = inserted_bucket_counts.get(bucket, 0) + 1
            conn.commit()

        finish_run(
            run_id,
            "completed",
            notes=dumps_payload(
                {
                    "inserted": inserted,
                    "candidates_found": len(candidates),
                    "deduped_candidates": len(deduped),
                    "bucket_counts": bucket_counts,
                    "inserted_bucket_counts": inserted_bucket_counts,
                    "limit": limit,
                    "confidence_threshold": confidence_threshold,
                }
            ),
        )
        return {
            "run_id": run_id,
            "inserted": inserted,
            "candidates_found": len(candidates),
            "deduped_candidates": len(deduped),
            "bucket_counts": bucket_counts,
            "inserted_bucket_counts": inserted_bucket_counts,
            "limit": limit,
            "confidence_threshold": confidence_threshold,
            "workspace_name": workspace_name,
        }
    except Exception as exc:
        logger.exception("Decision minority-label review seeding failed: %s", exc)
        finish_run(run_id, "failed", notes=dumps_payload({"error": str(exc)}))
        raise

def list_gold_labels(
    workspace_name: str,
    *,
    search_query: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Lists gold labels with optional text search.
    列出带有可选文本搜索的金标。
    """
    query = """
        SELECT g.*, r.raw_address_text, r.suggested_unit_number, r.building_type
        FROM gold_label g
        JOIN address_cleaning_result r ON g.workspace_name = r.workspace_name AND g.source_id = CAST(r.raw_id AS CHAR)
        WHERE g.workspace_name = %s
    """
    params = [workspace_name]
    
    if search_query:
        query += " AND r.raw_address_text LIKE %s"
        params.append(f"%{search_query}%")
        
    query += " ORDER BY g.created_at DESC LIMIT %s"
    params.append(limit)
    
    return fetch_all(query, tuple(params))

def update_gold_label(
    workspace_name: str,
    gold_label_id: int,
    *,
    building_type: str | None = None,
    suggested_unit_number: str | None = None,
) -> bool:
    """
    Manually updates a gold label, its associated cleaning result, and its structural JSON.
    手动更新金标、其关联的清洗结果以及其结构化 JSON。
    """
    import json
    # 1. Fetch current label state to update JSON
    # 1. 获取当前标签状态以更新 JSON
    label_row = fetch_all(
        "SELECT label_json FROM gold_label WHERE gold_label_id = %s AND workspace_name = %s",
        (gold_label_id, workspace_name)
    )
    if not label_row:
        return False
    
    current_payload = json.loads(label_row[0]["label_json"] or "{}")
    if building_type:
        current_payload["building_type"] = building_type
    if suggested_unit_number is not None:
        current_payload["unit_number"] = suggested_unit_number

    # 2. Update both tables in a transaction
    # 2. 在事务中更新两个表
    update_res_query = """
        UPDATE address_cleaning_result r
        JOIN gold_label g ON g.workspace_name = r.workspace_name AND g.source_id = CAST(r.raw_id AS CHAR)
        SET r.building_type = %s,
            r.suggested_unit_number = %s
        WHERE g.gold_label_id = %s AND g.workspace_name = %s
    """
    
    update_gold_query = """
        UPDATE gold_label
        SET review_status = 'accepted',
            label_source = 'human',
            label_json = %s,
            notes = CONCAT(COALESCE(notes, ''), ' [Manual Correction]')
        WHERE gold_label_id = %s AND workspace_name = %s
    """
    
    with db_cursor() as (conn, cursor):
        cursor.execute(update_res_query, (building_type, suggested_unit_number, gold_label_id, workspace_name))
        cursor.execute(update_gold_query, (json.dumps(current_payload), gold_label_id, workspace_name))
        conn.commit()
        return True
