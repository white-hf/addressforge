from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any

from addressforge.core.common import create_run, db_cursor, dumps_payload, fetch_all, finish_run, stable_holdout_bucket
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.core.utils import logger


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
    payload = _json_text(label_json)
    with db_cursor() as (conn, cursor):
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
            (workspace_name, source_name, source_id, task_type, payload, review_status, label_source, score, notes),
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
        query = """
            SELECT *
            FROM gold_label
            WHERE workspace_name = %s
              AND review_status = 'accepted'
              AND label_source = %s
        """
        params: list[Any] = [workspace_name, label_source_filter]
        if task_type:
            query += " AND task_type = %s"
            params.append(task_type)
        query += " ORDER BY gold_label_id ASC"
        labels = fetch_all(query, tuple(params))
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
    Seeds the active learning queue with a stratified sample of high-value tasks.
    使用高价值任务的分层样本填充主动学习队列。
    """
    run_id = create_run("ml_active_learning", notes=f"Stratified seed threshold={confidence_threshold}")
    logger.info("Starting stratified active learning seed: workspace=%s", workspace_name)
    
    try:
        # Define target strata (Iteration 9 requirements)
        # 定义目标层级 (迭代 9 要求)
        strata = [
            ("commercial", 0.20),
            ("multi_unit", 0.40),
            ("single_unit", 0.40)
        ]
        
        inserted = 0
        total_candidates_found = 0

        for b_type, ratio in strata:
            type_limit = max(1, int(limit * ratio))
            
            # Fetch candidates for specific building type with low confidence
            # 为特定建筑类型获取低置信度的候选样本
            candidates = fetch_all(
                """
                SELECT raw_id, decision, confidence, reason 
                FROM address_cleaning_result
                WHERE workspace_name = %s 
                  AND building_type = %s
                  AND (confidence <= %s OR decision = 'review')
                ORDER BY confidence ASC
                LIMIT %s
                """,
                (workspace_name, b_type, confidence_threshold, type_limit),
            )
            
            total_candidates_found += len(candidates)
            with db_cursor() as (conn, cursor):
                for row in candidates:
                    cursor.execute(
                        """
                        INSERT INTO active_learning_queue (
                            workspace_name, source_name, source_id, task_type, priority, confidence, reason, status
                        ) VALUES (%s, 'address_cleaning_result', %s, %s, %s, %s, %s, 'queued') AS new_row
                        ON DUPLICATE KEY UPDATE
                            priority = new_row.priority,
                            status = 'queued',
                            updated_at = NOW()
                        """,
                        (
                            workspace_name,
                            str(row["raw_id"]),
                            str(row.get("decision") or "validation"),
                            int(round((1.0 - float(row.get("confidence") or 0.0)) * 100)),
                            row.get("confidence"),
                            row.get("reason"),
                        ),
                    )
                    inserted += 1
                conn.commit()

        finish_run(run_id, "completed", notes=dumps_payload({"inserted": inserted, "stratified": True}))
        logger.info("Stratified seeding completed: %d total tasks queued.", inserted)
        
        return {
            "run_id": run_id,
            "inserted": inserted,
            "workspace_name": workspace_name,
            "candidates_found": total_candidates_found
        }

    except Exception as exc:
        logger.exception("Stratified seeding failed: %s", exc)
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
        with db_cursor() as (conn, cursor):
            for s in sorted_samples[:limit]:
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
                    (workspace_name, str(s["source_id"]), field, f"Priority error bucket: {field}")
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
        with db_cursor() as (conn, cursor):
            for row in candidates:
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
                        str(row["raw_id"]),
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
