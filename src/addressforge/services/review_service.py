from addressforge.learning.gold import list_active_learning_queue
from addressforge.learning.gold import upsert_gold_label
from addressforge.core.common import db_cursor, fetch_all
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.core.utils import logger
from addressforge.core.common import infer_structure_type
from addressforge.core.llm_refiner import LLMAddressRefiner
import json


_UNIT_HINT_TOKENS = (
    "APT", "APART", "SUITE", "STE", "UNIT", "#", "ROOM", "RM", "FLOOR", "FL",
    "BASEMENT", "BSMT", "LOWER", "UPPER", "PENTHOUSE", "PH", "GF", "GROUND FLOOR",
    "MAIN FLOOR", "MAIN FLR", "REAR", "FRONT", "SIDE",
)
_COMMERCIAL_HINT_TOKENS = (
    "MALL", "PLAZA", "SQUARE", "TOWER", "OFFICE", "CENTRE", "CENTER", "PARK LANE", "SCOTIA"
)


def _should_run_llm_prescreen(item: dict, detail: dict) -> bool:
    raw_text = str(detail.get("raw_address_text") or "").upper()
    building_type = str(detail.get("building_type") or "")
    confidence = float(item.get("confidence") or 0.0)
    task_type = str(item.get("task_type") or "")
    if task_type in {"unit_number", "building_type"}:
        return True
    if confidence <= 0.72:
        return True
    if building_type in {"commercial", "multi_unit"}:
        return True
    if any(token in raw_text for token in _UNIT_HINT_TOKENS):
        return True
    if any(token in raw_text for token in _COMMERCIAL_HINT_TOKENS):
        return True
    return False


def _current_parse_payload(detail: dict) -> dict:
    parser_json = detail.get("parser_json")
    if isinstance(parser_json, str):
        try:
            parser_json = json.loads(parser_json)
        except Exception:
            parser_json = None
    if isinstance(parser_json, dict):
        best = parser_json.get("best_candidate") or {}
        parsed = best.get("parsed") or {}
        if isinstance(parsed, dict):
            return parsed
    return {
        "street_number": None,
        "street_name": None,
        "unit_number": detail.get("suggested_unit_number"),
        "parse_confidence": float(detail.get("confidence") or 0.0),
        "feature_vector": {},
    }


def _run_llm_prescreen(item: dict, detail: dict) -> dict | None:
    if not _should_run_llm_prescreen(item, detail):
        return None
    raw_text = detail.get("raw_address_text")
    if not raw_text:
        return None
    current_result = _current_parse_payload(detail)
    try:
        suggestion = LLMAddressRefiner().refine_parsing(raw_text, current_result)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM prescreen failed for queue_id=%s: %s", item.get("queue_id"), exc)
        return None
    unit_number = suggestion.get("unit_number")
    building_type = suggestion.get("building_type") or infer_structure_type(
        raw_address_text=str(raw_text),
        parsed_unit_number=unit_number,
    )
    suggested_decision = suggestion.get("decision_hint") or (
        "review" if building_type in {"commercial", "multi_unit"} and not unit_number else "accept"
    )
    return {
        "street_number": suggestion.get("street_number"),
        "street_name": suggestion.get("street_name"),
        "unit_number": unit_number,
        "building_type": building_type,
        "decision": suggested_decision,
        "reasoning": suggestion.get("reasoning"),
    }


def _fetch_cleaning_detail(workspace_name: str, source_id: str) -> dict:
    is_numeric = str(source_id).isdigit()
    if is_numeric:
        details = fetch_all(
            "SELECT raw_address_text, suggested_unit_number, decision, building_type, reason, parser_json FROM address_cleaning_result WHERE workspace_name = %s AND raw_id = %s LIMIT 1",
            (workspace_name, int(source_id)),
        )
    else:
        details = fetch_all(
            "SELECT raw_address_text, suggested_unit_number, decision, building_type, reason, parser_json FROM address_cleaning_result WHERE workspace_name = %s AND CAST(raw_id AS CHAR) = %s LIMIT 1",
            (workspace_name, str(source_id)),
        )
    return details[0] if details else {}


def _load_prescreen_cache(workspace_name: str, source_name: str, source_id: str, task_type: str) -> dict | None:
    rows = fetch_all(
        """
        SELECT llm_json
        FROM review_prescreen_cache
        WHERE workspace_name = %s
          AND source_name = %s
          AND source_id = %s
          AND task_type = %s
        LIMIT 1
        """,
        (workspace_name, source_name, str(source_id), task_type),
    )
    if not rows:
        return None
    payload = rows[0].get("llm_json")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = None
    return payload if isinstance(payload, dict) else None


def _upsert_prescreen_cache(workspace_name: str, source_name: str, source_id: str, task_type: str, llm_prescreen: dict) -> None:
    payload = json.dumps(llm_prescreen, ensure_ascii=False)
    with db_cursor() as (conn, cursor):
        cursor.execute(
            """
            INSERT INTO review_prescreen_cache (
                workspace_name, source_name, source_id, task_type, llm_json, llm_model
            ) VALUES (%s, %s, %s, %s, %s, %s) AS new_row
            ON DUPLICATE KEY UPDATE
                llm_json = new_row.llm_json,
                llm_model = new_row.llm_model,
                updated_at = NOW()
            """,
            (workspace_name, source_name, str(source_id), task_type, payload, "qwen3:8b"),
        )
        conn.commit()


def batch_prescreen_review_queue(workspace_name=ADDRESSFORGE_WORKSPACE_NAME, limit=200, overwrite=False):
    raw_queue = list_active_learning_queue(workspace_name=workspace_name, status="queued", limit=limit)
    processed = 0
    cached = 0
    skipped = 0
    for item in raw_queue:
        source_name = str(item.get("source_name") or "address_cleaning_result")
        source_id = str(item.get("source_id") or "")
        task_type = str(item.get("task_type") or "review")
        if not source_id:
            skipped += 1
            continue
        existing = _load_prescreen_cache(workspace_name, source_name, source_id, task_type)
        if existing and not overwrite:
            cached += 1
            continue
        detail = _fetch_cleaning_detail(workspace_name, source_id)
        llm_prescreen = _run_llm_prescreen(item, detail)
        if not llm_prescreen:
            skipped += 1
            continue
        _upsert_prescreen_cache(workspace_name, source_name, source_id, task_type, llm_prescreen)
        processed += 1
    return {
        "workspace_name": workspace_name,
        "queued": len(raw_queue),
        "processed": processed,
        "cached": cached,
        "skipped": skipped,
    }

def get_review_queue(workspace_name=ADDRESSFORGE_WORKSPACE_NAME, limit=10):
    """
    Fetches the pending review queue and enriches it with detailed address metadata.
    获取待审核队列并使用详细的地址元数据进行增强。
    """
    # Fetch raw queue from database
    # 从数据库获取原始队列
    raw_queue = list_active_learning_queue(workspace_name=workspace_name, status="queued", limit=limit)
    
    if not raw_queue:
        return []

    # Enriched tasks collection
    # 增强后的任务集合
    enriched_tasks = []
    for item in raw_queue:
        task_id = item["queue_id"]
        source_id = item["source_id"]
        
        detail = _fetch_cleaning_detail(workspace_name, str(source_id))
        llm_prescreen = _load_prescreen_cache(
            workspace_name,
            str(item.get("source_name") or "address_cleaning_result"),
            str(source_id),
            str(item.get("task_type") or "review"),
        )
        if llm_prescreen is None:
            llm_prescreen = _run_llm_prescreen(item, detail)
            if llm_prescreen:
                _upsert_prescreen_cache(
                    workspace_name,
                    str(item.get("source_name") or "address_cleaning_result"),
                    str(source_id),
                    str(item.get("task_type") or "review"),
                    llm_prescreen,
                )
        llm_reasoning = (llm_prescreen or {}).get("reasoning")
        llm_summary = None
        if llm_prescreen:
            llm_summary = (
                f"LLM prescreen: {llm_prescreen.get('building_type') or 'unknown'}"
                f", unit={llm_prescreen.get('unit_number') or 'none'}"
                f", suggested decision={llm_prescreen.get('decision') or 'review'}."
            )
        
        enriched_tasks.append({
            "task_id": task_id,
            "task_title": detail.get("raw_address_text") or f"Source ID: {source_id}",
            "task_summary": f"System Suggestion: {detail.get('decision', 'N/A')} - {detail.get('reason', 'Verification Required')}",
            "task_type": item["task_type"],
            "priority": item["priority"],
            "confidence": item["confidence"],
            "raw_address_text": detail.get("raw_address_text", ""),
            "building_type": detail.get("building_type"),
            "suggested_unit_number": detail.get("suggested_unit_number"),
            "llm_prescreen": llm_prescreen,
            "llm_advice": llm_reasoning or "LLM prescreen not triggered for this sample.",
            "audit_tip": llm_summary or "Review the address fact first, then use system suggestion as guidance.",
            "risk_points": ["Partial street match", "Low confidence score (< 0.6)", "Ambiguous abbreviation in source"],
            "evidence": [
                {"label": "System Decision", "value": f"Action: {detail.get('decision')} | Confidence: {item['confidence']}"},
                {"label": "Reason Summary", "value": item["reason"] or detail.get("reason") or "Uncertainty sampling"},
                *(
                    [{
                        "label": "LLM Prescreen",
                        "value": llm_summary,
                    }]
                    if llm_summary else []
                )
            ]
        })
        
    return enriched_tasks

def submit_review(task_id, decision, notes, building_type=None, unit_number=None):
    normalized_decision = "accept" if decision == "correct" else decision
    queue_rows = fetch_all(
        """
        SELECT *
        FROM active_learning_queue
        WHERE queue_id = %s
        LIMIT 1
        """,
        (task_id,),
    )
    if not queue_rows:
        return {"status": "error", "task_id": task_id, "error": "queue item not found"}

    queue_item = queue_rows[0]
    workspace_name = queue_item["workspace_name"]
    source_id = str(queue_item["source_id"])
    task_type = queue_item["task_type"]
    # Pull cleaning results using proper type handling for source_id
    # 使用正确的 source_id 类型处理提取清洗结果
    is_numeric = str(source_id).isdigit()
    if is_numeric:
        cleaning_rows = fetch_all(
            """
            SELECT decision, building_type, suggested_unit_number, reason
            FROM address_cleaning_result
            WHERE workspace_name = %s AND raw_id = %s
            LIMIT 1
            """,
            (workspace_name, int(source_id)),
        )
    else:
        # Fallback for string-based IDs
        # 针对字符串类型 ID 的回退方案
        cleaning_rows = fetch_all(
            """
            SELECT decision, building_type, suggested_unit_number, reason
            FROM address_cleaning_result
            WHERE workspace_name = %s AND CAST(raw_id AS CHAR) = %s
            LIMIT 1
            """,
            (workspace_name, str(source_id)),
        )
    
    cleaning = cleaning_rows[0] if cleaning_rows else {}
    resolved_building_type = building_type or cleaning.get("building_type")
    resolved_unit_number = unit_number if unit_number is not None else cleaning.get("suggested_unit_number")
    label_json = {
        "decision": normalized_decision,
        "building_type": resolved_building_type,
        "unit_number": resolved_unit_number,
        "reason": cleaning.get("reason"),
        "review_action": decision,
    }
    label = upsert_gold_label(
        workspace_name=workspace_name,
        source_name=str(queue_item.get("source_name") or "active_learning_queue"),
        source_id=source_id,
        task_type=task_type,
        label_json=label_json,
        review_status="accepted",
        label_source="human",
        score=queue_item.get("confidence"),
        notes=notes,
    )
    with db_cursor() as (conn, cursor):
        cursor.execute(
            """
            UPDATE active_learning_queue
            SET status = 'labeled', updated_at = NOW()
            WHERE queue_id = %s
            """,
            (task_id,),
        )
        conn.commit()
    return {"status": "success", "task_id": task_id, "decision": normalized_decision, "review_action": decision, "label": label}
