from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from addressforge.api.server import AddressRequest, service as address_service
from addressforge.core.common import db_cursor, dumps_payload, fetch_all, has_numbered_road_signal
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.core.utils import logger
from addressforge.control.settings import get_setting
from addressforge.models import get_workspace

STAGES = ("normalize", "parse", "validate", "publish")


from decimal import Decimal

class DecimalEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)

def _set_setting(workspace_name: str, setting_key: str, setting_value: Any) -> None:
    if isinstance(setting_value, (dict, list)):
        raw_value = json.dumps(setting_value, ensure_ascii=False, cls=DecimalEncoder)
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


def _build_request(raw_row: dict[str, Any], *, profile: str | None = None) -> AddressRequest:
    return AddressRequest(
        raw_address_text=str(raw_row.get("raw_address_text") or ""),
        city=raw_row.get("city"),
        province=raw_row.get("province"),
        postal_code=raw_row.get("postal_code"),
        country_code=str(raw_row.get("country_code") or "CA"),
        profile=profile,
        latitude=raw_row.get("latitude"),
        longitude=raw_row.get("longitude"),
    )


def _get_existing_result(workspace_name: str, raw_id: int) -> dict[str, Any] | None:
    rows = fetch_all(
        """
        SELECT *
        FROM address_cleaning_result
        WHERE workspace_name = %s AND raw_id = %s
        LIMIT 1
        """,
        (workspace_name, raw_id),
    )
    return rows[0] if rows else None


def _coerce_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, str):
            try:
                reparsed = json.loads(parsed)
            except Exception:
                return {}
            return reparsed if isinstance(reparsed, dict) else {}
    return {}


def _extract_feature_flags(raw_text: str, building_type: str, parsed: dict) -> dict[str, int]:
    """
    Identifies high-value structural patterns for strategic sampling.
    识别用于战略抽样的高价值结构模式。
    """
    import re
    text = str(raw_text or "").upper()
    flags = {
        "has_double_number": 0,
        "is_numbered_road": 0,
        "has_explicit_unit": 0,
    }

    text_without_postal = re.sub(r"\b[A-Z]\d[A-Z]\s*\d[A-Z]\d\b", " ", text)

    # 1. Detect double-number boundary patterns while excluding postal-code noise.
    # 1. 检测双数字边界模式，同时排除邮编噪音。
    if re.search(r"^\s*\d+[A-Z]?\s+.+\s+\d+[A-Z]?\s+[A-Z][A-Z .'-]+\s+(?:NS|NB|ON|QC|PE|NL|MB|SK|AB|BC|YT|NT|NU)\b", text_without_postal):
        flags["has_double_number"] = 1
    elif re.search(r"^\s*\d+[A-Z]?\s+.+,\s*\d+[A-Z]?\s+[A-Z][A-Z .'-]+\s+(?:NS|NB|ON|QC|PE|NL|MB|SK|AB|BC|YT|NT|NU)\b", text_without_postal):
        flags["has_double_number"] = 1

    # 2. Detect Numbered Roads (e.g., Highway 325)
    # 2. 检测编号道路 (例如 Highway 325)
    street_name = str(parsed.get("street_name") or "").upper()
    if has_numbered_road_signal(street_name) or has_numbered_road_signal(text):
        flags["is_numbered_road"] = 1

    # 3. Has Explicit Unit Key (e.g., APT, UNIT, SUITE)
    # 3. 包含显式单元关键字 (例如 APT, UNIT, SUITE)
    if re.search(r"(?:\b(?:APT|APARTMENT|UNIT|SUITE|STE|ROOM|RM|FLOOR|FL|BASEMENT|BSMT)\b|#\s*[A-Z0-9]+)", text):
        flags["has_explicit_unit"] = 1

    return flags


def _upsert_stage_result(
    workspace_name: str,
    raw_row: dict[str, Any],
    *,
    checkpoint_stage: str,
    checkpoint_status: str,
    normalize_result: dict[str, Any] | None = None,
    parse_result: dict[str, Any] | None = None,
    validation_result: dict[str, Any] | None = None,
    checkpoint_error: str | None = None,
) -> None:
    parse_payload = _coerce_json_object(parse_result)
    validation = _coerce_json_object(validation_result)
    canonical = validation.get("canonical") or {}
    reference = validation.get("reference") or {}
    
    # Extract structural feature flags for future strategic sampling
    # 提取结构化特征标记以用于未来的战略抽样
    best_candidate = parse_payload.get("best_candidate") or {}
    parsed_data = best_candidate.get("parsed") or {}
    feature_flags = _extract_feature_flags(
        str(raw_row.get("raw_address_text") or ""), 
        validation.get("building_type", "unknown"), 
        parsed_data
    )

    with db_cursor() as (conn, cursor):
        cursor.execute(
            """
            INSERT INTO address_cleaning_result (
                workspace_name, raw_id, raw_address_text, normalize_json, decision, confidence, reason,
                building_type, suggested_unit_number, base_address_key, full_address_key,
                parser_json, validation_json, reference_json, feature_flags,
                checkpoint_stage, checkpoint_status, checkpoint_error
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) AS new_row
            ON DUPLICATE KEY UPDATE
                raw_address_text = new_row.raw_address_text,
                normalize_json = COALESCE(new_row.normalize_json, address_cleaning_result.normalize_json),
                decision = COALESCE(new_row.decision, address_cleaning_result.decision),
                confidence = COALESCE(new_row.confidence, address_cleaning_result.confidence),
                reason = COALESCE(new_row.reason, address_cleaning_result.reason),
                building_type = COALESCE(new_row.building_type, address_cleaning_result.building_type),
                suggested_unit_number = COALESCE(new_row.suggested_unit_number, address_cleaning_result.suggested_unit_number),
                base_address_key = COALESCE(new_row.base_address_key, address_cleaning_result.base_address_key),
                full_address_key = COALESCE(new_row.full_address_key, address_cleaning_result.full_address_key),
                parser_json = COALESCE(new_row.parser_json, address_cleaning_result.parser_json),
                validation_json = COALESCE(new_row.validation_json, address_cleaning_result.validation_json),
                reference_json = COALESCE(new_row.reference_json, address_cleaning_result.reference_json),
                feature_flags = new_row.feature_flags,
                checkpoint_stage = new_row.checkpoint_stage,
                checkpoint_status = new_row.checkpoint_status,
                checkpoint_error = new_row.checkpoint_error,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                workspace_name,
                int(raw_row["raw_id"]),
                raw_row.get("raw_address_text") or "",
                dumps_payload(normalize_result) if normalize_result else None,
                validation.get("decision") or "pending",
                validation.get("confidence"),
                validation.get("reason"),
                validation.get("building_type"),
                validation.get("suggested_unit_number"),
                canonical.get("base_address_key"),
                canonical.get("full_address_key"),
                dumps_payload(parse_payload) if parse_payload else None,
                dumps_payload(validation) if validation else None,
                dumps_payload(reference) if reference else None,
                dumps_payload(feature_flags),
                checkpoint_stage,
                checkpoint_status,
                checkpoint_error,
            ),
        )
        conn.commit()


def _set_stage_progress(workspace_name: str, stage: str, raw_id: int) -> None:
    _set_setting(workspace_name, f"cleaning.{stage}.last_raw_id", raw_id)
    _set_setting(workspace_name, "cleaning.current_stage", stage)
    _set_setting(workspace_name, "cleaning.current_raw_id", raw_id)


def _mark_pipeline_result(
    workspace_name: str,
    *,
    batch_size: int,
    records_seen: int,
    records_processed: int,
    next_raw_id: int,
    last_validation: dict[str, Any] | None,
) -> None:
    _set_setting(workspace_name, "cleaning.last_run_at", datetime.utcnow().isoformat(sep=" "))
    _set_setting(workspace_name, "cleaning.last_batch_size", batch_size)
    _set_setting(workspace_name, "cleaning.last_processed", records_processed)
    _set_setting(workspace_name, "cleaning.publish.last_raw_id", next_raw_id)
    _set_setting(
        workspace_name,
        "cleaning.last_result",
        {
            "records_seen": records_seen,
            "records_processed": records_processed,
            "next_raw_id": next_raw_id,
            "last_stage": "publish" if records_processed else None,
        },
    )
    _set_setting(workspace_name, "cleaning.last_error", "")
    _set_setting(workspace_name, "cleaning.last_validation", last_validation or {})


def _mark_pipeline_error(workspace_name: str, *, raw_id: int, stage: str, error_text: str) -> None:
    _set_setting(workspace_name, "cleaning.current_stage", stage)
    _set_setting(workspace_name, "cleaning.current_raw_id", raw_id)
    _set_setting(workspace_name, "cleaning.last_error", error_text)
    _set_setting(
        workspace_name,
        "cleaning.last_result",
        {
            "failed_raw_id": raw_id,
            "failed_stage": stage,
            "error": error_text,
        },
    )


def _safe_checkpoint_failure(
    workspace_name: str,
    row: dict[str, Any],
    *,
    current_stage: str,
    normalize_result: dict[str, Any] | None,
    parse_result: dict[str, Any] | None,
    validation_result: dict[str, Any] | None,
    error_text: str,
) -> None:
    try:
        _upsert_stage_result(
            workspace_name,
            row,
            checkpoint_stage=current_stage or "unknown",
            checkpoint_status="failed",
            normalize_result=normalize_result if isinstance(normalize_result, dict) else None,
            parse_result=parse_result if isinstance(parse_result, dict) else None,
            validation_result=validation_result if isinstance(validation_result, dict) else None,
            checkpoint_error=error_text,
        )
    except Exception as checkpoint_exc:  # noqa: BLE001
        logger.warning("Failed to persist cleaning failure checkpoint: %s", checkpoint_exc)

    try:
        _mark_pipeline_error(
            workspace_name,
            raw_id=int(row.get("raw_id") or 0),
            stage=current_stage or "unknown",
            error_text=error_text,
        )
    except Exception as mark_exc:  # noqa: BLE001
        logger.warning("Failed to persist cleaning pipeline error status: %s", mark_exc)


def run_cleaning_once(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME, batch_size: int = 1000) -> dict[str, Any]:
    workspace = get_workspace(workspace_name) or {}
    workspace_profile = workspace.get("default_profile")
    last_published_raw_id = int(get_setting(workspace_name, "cleaning.publish.last_raw_id", 0) or 0)
    rows = fetch_all(
        """
        SELECT *
        FROM raw_address_record
        WHERE raw_id > %s AND is_active = 1 AND workspace_name = %s
        ORDER BY raw_id ASC
        LIMIT %s
        """,
        (last_published_raw_id, workspace_name, batch_size),
    )
    records_seen = len(rows)
    has_more = records_seen >= batch_size
    records_processed = 0
    next_raw_id = last_published_raw_id
    last_validation: dict[str, Any] | None = None

    for row in rows:
        raw_id = int(row["raw_id"])
        current_stage = "normalize"
        request = _build_request(row, profile=str(workspace_profile) if workspace_profile else None)
        existing = _get_existing_result(workspace_name, raw_id) or {}
        
        # Safely parse JSON fields from database
        # 安全地从数据库解析 JSON 字段
        def _parse_json(val: Any) -> dict | None:
            if not val: return None
            if isinstance(val, dict): return val
            try:
                return json.loads(str(val))
            except Exception:
                return None

        normalize_result = _parse_json(existing.get("normalize_json"))
        parse_result = _parse_json(existing.get("parser_json"))
        validation_result = _parse_json(existing.get("validation_json"))
        try:
            if not normalize_result:
                current_stage = "normalize"
                _set_stage_progress(workspace_name, "normalize", raw_id)
                normalize_result = address_service.normalize(request)
                _upsert_stage_result(
                    workspace_name,
                    row,
                    checkpoint_stage="normalize",
                    checkpoint_status="running",
                    normalize_result=normalize_result,
                )

            if not parse_result:
                current_stage = "parse"
                _set_stage_progress(workspace_name, "parse", raw_id)
                parse_result = address_service.parse(request)
                _upsert_stage_result(
                    workspace_name,
                    row,
                    checkpoint_stage="parse",
                    checkpoint_status="running",
                    normalize_result=normalize_result,
                    parse_result=parse_result,
                )

            if not validation_result:
                current_stage = "validate"
                _set_stage_progress(workspace_name, "validate", raw_id)
                validation_result = address_service.validate(request)
                
                # Active LLM Integration (Iteration 8 & Task 2)
                # 主动 LLM 集成 (迭代 8 与任务 2)
                from addressforge.core.llm_refiner import LLMAddressRefiner, should_trigger_llm
                if should_trigger_llm(validation_result):
                    refiner = LLMAddressRefiner()
                    llm_suggestion = refiner.refine_parsing(row.get("raw_address_text"), parse_result)
                    
                    # Update decision if LLM provides a confident correction
                    # 如果 LLM 提供了高置信度的修正，则更新决策
                    validation_result["llm_refinement"] = llm_suggestion
                    validation_result["reason"] = f"LLM REFINED: {llm_suggestion['reasoning']}"
                    validation_result["confidence"] = min(0.95, (validation_result.get("confidence") or 0) + 0.2)

                _upsert_stage_result(
                    workspace_name,
                    row,
                    checkpoint_stage="validate",
                    checkpoint_status="running",
                    normalize_result=normalize_result,
                    parse_result=parse_result,
                    validation_result=validation_result,
                )

            current_stage = "publish"
            _set_stage_progress(workspace_name, "publish", raw_id)
            _upsert_stage_result(
                workspace_name,
                row,
                checkpoint_stage="publish",
                checkpoint_status="completed",
                normalize_result=normalize_result,
                parse_result=parse_result,
                validation_result=validation_result,
            )
            next_raw_id = raw_id
            records_processed += 1
            last_validation = validation_result
        except Exception as exc:  # noqa: BLE001
            _safe_checkpoint_failure(
                workspace_name,
                row,
                current_stage=current_stage,
                normalize_result=normalize_result if isinstance(normalize_result, dict) else None,
                parse_result=parse_result if isinstance(parse_result, dict) else None,
                validation_result=validation_result if isinstance(validation_result, dict) else None,
                error_text=str(exc),
            )
            raise

    _mark_pipeline_result(
        workspace_name,
        batch_size=batch_size,
        records_seen=records_seen,
        records_processed=records_processed,
        next_raw_id=next_raw_id,
        last_validation=last_validation,
    )
    return {
        "workspace_name": workspace_name,
        "batch_size": batch_size,
        "last_published_raw_id": last_published_raw_id,
        "next_raw_id": next_raw_id,
        "records_seen": records_seen,
        "records_processed": records_processed,
        "has_more": has_more,
        "checkpoint_stage": "publish" if records_processed else None,
        "last_validation": last_validation,
    }


def main() -> None:
    print(run_cleaning_once())


if __name__ == "__main__":
    main()
