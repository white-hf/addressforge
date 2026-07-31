from __future__ import annotations

import logging
from typing import Any, Dict, List

from addressforge.core.common import (
    create_run,
    db_cursor,
    dumps_payload,
    fetch_all,
    finish_run,
)
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.models import build_release_readiness_report, get_active_model
from addressforge.services.runtime_bundle import build_runtime_bundle_from_model_row

logger = logging.getLogger(__name__)

def _load_model_runtime(workspace_name: str, model_version: str) -> dict[str, Any]:
    """
    Internal helper to load a model version into memory for runtime inference.
    Returns a full runtime bundle (profile, parsers, policy, services).
    """
    logger.info("Loading model runtime bundle: %s", model_version)
    model_row = None
    if model_version:
        rows = fetch_all(
            """
            SELECT *
            FROM model_registry
            WHERE workspace_name = %s AND model_version = %s
            ORDER BY is_default DESC, updated_at DESC, created_at DESC
            LIMIT 1
            """,
            (workspace_name, model_version),
        )
        model_row = rows[0] if rows else None
    else:
        model_row = get_active_model(workspace_name)
    
    if not model_row:
        return {"ok": False, "reason": "model_not_found"}

    return build_runtime_bundle_from_model_row(model_row, mode="governed")


def _persist_replay_evidence(
    *,
    workspace_name: str,
    run_id: int,
    candidate_model: dict[str, Any],
    active_model: dict[str, Any],
    requested_count: int,
    processed_count: int,
    failure_count: int,
    disagreement_count: int,
    decision_match_rate: float,
    building_type_match_rate: float,
    unit_number_match_rate: float,
    status: str,
    runtime_identity: dict[str, Any],
    evidence_rows: list[tuple[Any, ...]],
) -> int:
    """Persist the replay summary and every row-level success/failure atomically."""
    with db_cursor() as (conn, cursor):
        cursor.execute(
            """
            INSERT INTO historical_replay_run (
                workspace_name, run_id, model_name, model_version,
                candidate_model_id, active_model_id,
                requested_count, processed_count, failure_count, disagreement_count,
                decision_match_rate, building_type_match_rate, unit_number_match_rate,
                status, error_text,
                candidate_runtime_identity_json, active_runtime_identity_json,
                completed_at
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                NOW()
            ) AS new_run
            ON DUPLICATE KEY UPDATE
                replay_id = LAST_INSERT_ID(replay_id),
                model_name = new_run.model_name,
                model_version = new_run.model_version,
                candidate_model_id = new_run.candidate_model_id,
                active_model_id = new_run.active_model_id,
                requested_count = new_run.requested_count,
                processed_count = new_run.processed_count,
                failure_count = new_run.failure_count,
                disagreement_count = new_run.disagreement_count,
                decision_match_rate = new_run.decision_match_rate,
                building_type_match_rate = new_run.building_type_match_rate,
                unit_number_match_rate = new_run.unit_number_match_rate,
                status = new_run.status,
                error_text = new_run.error_text,
                candidate_runtime_identity_json = new_run.candidate_runtime_identity_json,
                active_runtime_identity_json = new_run.active_runtime_identity_json,
                completed_at = NOW()
            """,
            (
                workspace_name,
                run_id,
                candidate_model.get("model_name") or "candidate",
                candidate_model.get("model_version"),
                candidate_model.get("model_id"),
                active_model.get("model_id"),
                requested_count,
                processed_count,
                failure_count,
                disagreement_count,
                decision_match_rate,
                building_type_match_rate,
                unit_number_match_rate,
                status,
                None,
                dumps_payload(runtime_identity.get("candidate")),
                dumps_payload(runtime_identity.get("active")),
            ),
        )
        replay_id = int(cursor.lastrowid or 0)
        if evidence_rows:
            cursor.executemany(
                """
                INSERT INTO historical_replay_result (
                    workspace_name, run_id, raw_id,
                    current_decision, current_building_type, current_unit_number,
                    candidate_decision, candidate_building_type, candidate_unit_number,
                    active_decision, active_building_type, active_unit_number,
                    decision_match, building_type_match, unit_number_match,
                    candidate_vs_active_different,
                    candidate_vs_current_different, active_vs_current_different,
                    processing_status, error_text,
                    current_output_json, candidate_output_json, active_output_json
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s
                ) AS new_result
                ON DUPLICATE KEY UPDATE
                    current_decision = new_result.current_decision,
                    current_building_type = new_result.current_building_type,
                    current_unit_number = new_result.current_unit_number,
                    candidate_decision = new_result.candidate_decision,
                    candidate_building_type = new_result.candidate_building_type,
                    candidate_unit_number = new_result.candidate_unit_number,
                    active_decision = new_result.active_decision,
                    active_building_type = new_result.active_building_type,
                    active_unit_number = new_result.active_unit_number,
                    decision_match = new_result.decision_match,
                    building_type_match = new_result.building_type_match,
                    unit_number_match = new_result.unit_number_match,
                    candidate_vs_active_different = new_result.candidate_vs_active_different,
                    candidate_vs_current_different = new_result.candidate_vs_current_different,
                    active_vs_current_different = new_result.active_vs_current_different,
                    processing_status = new_result.processing_status,
                    error_text = new_result.error_text,
                    current_output_json = new_result.current_output_json,
                    candidate_output_json = new_result.candidate_output_json,
                    active_output_json = new_result.active_output_json
                """,
                evidence_rows,
            )
        conn.commit()
    return replay_id


def run_historical_replay(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    candidate_version: str | None = None,
    limit: int = 2000
) -> dict[str, Any]:
    """
    Executes true historical replay by running actual candidate vs active inference.
    通过运行实际的候选与活动推理来执行真实的历史重放。
    """
    from addressforge.api.server import AddressPlatformService, AddressRequest
    
    run_id = create_run("historical_replay", notes=f"True execution replay: candidate={candidate_version}")
    logger.info("Starting True Replay for workspace: %s", workspace_name)
    
    try:
        candidate_model_rows = fetch_all(
            """
            SELECT *
            FROM model_registry
            WHERE workspace_name = %s AND model_version = %s
            ORDER BY is_default DESC, updated_at DESC, created_at DESC
            LIMIT 1
            """,
            (workspace_name, candidate_version),
        ) if candidate_version else []
        candidate_model = candidate_model_rows[0] if candidate_model_rows else None
        active_model = get_active_model(workspace_name)
        candidate_runtime = _load_model_runtime(workspace_name, candidate_version)
        active_runtime = _load_model_runtime(workspace_name, None)
        
        if not candidate_runtime.get("ok"):
            raise ValueError(f"candidate runtime unavailable: {workspace_name}/{candidate_version} - {candidate_runtime.get('reason')}")
        if not active_runtime.get("ok"):
            raise ValueError(f"active runtime unavailable: {workspace_name} - {active_runtime.get('reason')}")
            
        candidate_service = AddressPlatformService(
            default_profile=candidate_runtime["profile"],
            default_parsers=candidate_runtime["parsers"],
            decision_policy=candidate_runtime["decision_policy"],
            model_service=candidate_runtime["model_service"],
            reranker_service=candidate_runtime["reranker_service"],
            allow_local_policy_override=False,
        )
        active_service = AddressPlatformService(
            default_profile=active_runtime["profile"],
            default_parsers=active_runtime["parsers"],
            decision_policy=active_runtime["decision_policy"],
            model_service=active_runtime["model_service"],
            reranker_service=active_runtime["reranker_service"],
            allow_local_policy_override=False,
        )
        runtime_identity = {
            "candidate": candidate_runtime.get("runtime_identity")
            or {
                "decision_model": candidate_runtime["model_service"].describe_runtime(),
                "reranker_model": candidate_runtime["reranker_service"].describe_runtime(),
                "profile": candidate_runtime["profile"],
                "parsers": list(candidate_runtime["parsers"]),
            },
            "active": active_runtime.get("runtime_identity")
            or {
                "decision_model": active_runtime["model_service"].describe_runtime(),
                "reranker_model": active_runtime["reranker_service"].describe_runtime(),
                "profile": active_runtime["profile"],
                "parsers": list(active_runtime["parsers"]),
            },
        }

        # 2. Fetch historical records
        # 2. 获取历史记录
        query = """
            SELECT
                r.raw_id,
                r.raw_address_text,
                r.city,
                r.province,
                r.postal_code,
                acr.decision AS current_decision,
                acr.building_type AS current_building_type,
                acr.suggested_unit_number AS current_unit_number
            FROM raw_address_record r
            LEFT JOIN address_cleaning_result acr
              ON acr.workspace_name = r.workspace_name
             AND acr.raw_id = r.raw_id
            WHERE r.workspace_name = %s
              AND acr.raw_id IS NOT NULL
            ORDER BY r.raw_id DESC
            LIMIT %s
        """
        records = fetch_all(query, (workspace_name, limit))
        
        total_processed = 0
        failures = 0
        decision_matches = 0
        building_type_matches = 0
        unit_number_matches = 0
        candidate_vs_active_diffs = 0
        
        active_current_matches = 0
        candidate_current_matches = 0
        
        mismatches: list[dict[str, Any]] = []
        failure_samples: list[dict[str, Any]] = []
        evidence_rows: list[tuple[Any, ...]] = []
        
        for row in records:
            raw_id = row["raw_id"]
            raw_text = row["raw_address_text"]
            current_dec = row["current_decision"]
            current_bt = row["current_building_type"]
            current_un = row["current_unit_number"]
            
            try:
                # Candidate Inference
                cand_req = AddressRequest(raw_address_text=raw_text, city=row.get("city"), province=row.get("province"), postal_code=row.get("postal_code"))
                cand_res = candidate_service.validate(cand_req)
                
                # Active Inference
                act_req = AddressRequest(raw_address_text=raw_text, city=row.get("city"), province=row.get("province"), postal_code=row.get("postal_code"))
                act_res = active_service.validate(act_req)
                
                # Compare
                cand_dec = cand_res.get("decision")
                cand_bt = cand_res.get("building_type")
                cand_un_res = cand_res.get("suggested_unit_number")
                
                act_dec = act_res.get("decision")
                act_bt = act_res.get("building_type")
                act_un_res = act_res.get("suggested_unit_number")
                
                is_diff = (cand_dec != act_dec or cand_bt != act_bt or cand_un_res != act_un_res)
                candidate_vs_current = (
                    cand_dec != current_dec
                    or cand_bt != current_bt
                    or cand_un_res != current_un
                )
                active_vs_current = (
                    act_dec != current_dec
                    or act_bt != current_bt
                    or act_un_res != current_un
                )
                if is_diff:
                    candidate_vs_active_diffs += 1
                    if len(mismatches) < 50:
                        mismatches.append({
                            "raw_id": raw_id,
                            "raw_text": raw_text,
                            "candidate": {"decision": cand_dec, "building_type": cand_bt, "unit_number": cand_un_res},
                            "active": {"decision": act_dec, "building_type": act_bt, "unit_number": act_un_res},
                            "current": {"decision": current_dec, "building_type": current_bt, "unit_number": current_un}
                        })
                
                decision_matches += int(cand_dec == act_dec)
                building_type_matches += int(cand_bt == act_bt)
                unit_number_matches += int(cand_un_res == act_un_res)
                
                active_current_matches += int(act_dec == current_dec)
                candidate_current_matches += int(cand_dec == current_dec)
                
                total_processed += 1
                current_output = {
                    "decision": current_dec,
                    "building_type": current_bt,
                    "unit_number": current_un,
                }
                candidate_output = {
                    "decision": cand_dec,
                    "building_type": cand_bt,
                    "unit_number": cand_un_res,
                }
                active_output = {
                    "decision": act_dec,
                    "building_type": act_bt,
                    "unit_number": act_un_res,
                }
                evidence_rows.append(
                    (
                        workspace_name,
                        run_id,
                        raw_id,
                        current_dec,
                        current_bt,
                        current_un,
                        cand_dec,
                        cand_bt,
                        cand_un_res,
                        act_dec,
                        act_bt,
                        act_un_res,
                        int(cand_dec == act_dec),
                        int(cand_bt == act_bt),
                        int(cand_un_res == act_un_res),
                        int(is_diff),
                        int(candidate_vs_current),
                        int(active_vs_current),
                        "success",
                        None,
                        dumps_payload(current_output),
                        dumps_payload(candidate_output),
                        dumps_payload(active_output),
                    )
                )
                
            except Exception as e:
                logger.error("Replay failure on raw_id %d: %s", raw_id, e)
                failures += 1
                error_text = str(e)
                if len(failure_samples) < 50:
                    failure_samples.append(
                        {
                            "raw_id": raw_id,
                            "raw_text": raw_text,
                            "error": error_text,
                        }
                    )
                evidence_rows.append(
                    (
                        workspace_name,
                        run_id,
                        raw_id,
                        current_dec,
                        current_bt,
                        current_un,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        0,
                        0,
                        0,
                        1,
                        0,
                        0,
                        "failed",
                        error_text[:65535],
                        dumps_payload(
                            {
                                "decision": current_dec,
                                "building_type": current_bt,
                                "unit_number": current_un,
                            }
                        ),
                        None,
                        None,
                    )
                )
                
        # 3. Finalize and Save Metrics
        # 3. 完成并保存指标
        consistency_score = round(decision_matches / total_processed, 4) if total_processed > 0 else 0.0
        decision_match_rate = round(decision_matches / total_processed, 4) if total_processed > 0 else 0.0
        building_type_match_rate = round(building_type_matches / total_processed, 4) if total_processed > 0 else 0.0
        unit_number_match_rate = round(unit_number_matches / total_processed, 4) if total_processed > 0 else 0.0
        disagreement_rate = round(candidate_vs_active_diffs / total_processed, 4) if total_processed > 0 else 0.0
        
        active_current_match_rate = round(active_current_matches / total_processed, 4) if total_processed > 0 else 0.0
        candidate_current_match_rate = round(candidate_current_matches / total_processed, 4) if total_processed > 0 else 0.0
        
        replay_status = (
            "completed_empty"
            if not records
            else "completed_with_failures"
            if failures
            else "completed"
        )
        replay_id = _persist_replay_evidence(
            workspace_name=workspace_name,
            run_id=run_id,
            candidate_model=candidate_model or {},
            active_model=active_model or {},
            requested_count=len(records),
            processed_count=total_processed,
            failure_count=failures,
            disagreement_count=candidate_vs_active_diffs,
            decision_match_rate=decision_match_rate,
            building_type_match_rate=building_type_match_rate,
            unit_number_match_rate=unit_number_match_rate,
            status=replay_status,
            runtime_identity=runtime_identity,
            evidence_rows=evidence_rows,
        )

        metadata = {
            "replay_id": replay_id,
            "requested_count": len(records),
            "processed_count": total_processed,
            "failure_count": failures,
            "disagreement_count": candidate_vs_active_diffs,
            "consistency_score": consistency_score,
            "decision_match_rate": decision_match_rate,
            "building_type_match_rate": building_type_match_rate,
            "unit_number_match_rate": unit_number_match_rate,
            "disagreement_rate": disagreement_rate,
            "active_current_match_rate": active_current_match_rate,
            "candidate_current_match_rate": candidate_current_match_rate,
            "active_model_version": (active_model or {}).get("model_version"),
            "candidate_version": candidate_version,
            "runtime_identity": runtime_identity,
            "status": replay_status,
        }
        
        finish_run(run_id, "completed", notes=dumps_payload(metadata))
        logger.info("True Replay finished. Consistency: %f, Failures: %d", consistency_score, failures)
        
        return {
            "status": replay_status,
            "run_id": run_id,
            "processed": total_processed,
            "requested": len(records),
            "failures": failures,
            "mismatch_count": candidate_vs_active_diffs,
            "consistency_score": consistency_score,
            "decision_match_rate": decision_match_rate,
            "building_type_match_rate": building_type_match_rate,
            "unit_number_match_rate": unit_number_match_rate,
            "disagreement_rate": disagreement_rate,
            "active_current_match_rate": active_current_match_rate,
            "candidate_current_match_rate": candidate_current_match_rate,
            "mismatches": mismatches,
            "failure_samples": failure_samples,
            "active_model_version": (active_model or {}).get("model_version"),
            "candidate_version": candidate_version,
            "runtime_identity": runtime_identity
        }
    except Exception as exc:
        logger.exception("Historical replay failed: %s", exc)
        finish_run(run_id, "failed", notes=str(exc))
        raise

def get_release_readiness_report(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME) -> dict[str, Any]:
    """Return the same governed release report used by Promote."""
    latest_eval = fetch_all(
        """
        SELECT *
        FROM model_registry
        WHERE workspace_name = %s
          AND status IN ('evaluated', 'trained')
          AND is_default = 0
        ORDER BY updated_at DESC, created_at DESC
        LIMIT 1
        """,
        (workspace_name,)
    )
    
    if not latest_eval:
        return {"ready": False, "reason": "No evaluation data found"}
    return build_release_readiness_report(latest_eval[0])

def get_mismatch_samples(run_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Retrieves detailed samples where candidate and active models disagreed.
    检索候选模型与活动模型不一致的详细样本。
    """
    query = """
        SELECT hrr.*, r.raw_address_text
        FROM historical_replay_result hrr
        JOIN raw_address_record r
          ON hrr.workspace_name = r.workspace_name
         AND hrr.raw_id = r.raw_id
        WHERE hrr.run_id = %s AND hrr.candidate_vs_active_different = 1
        ORDER BY hrr.replay_result_id ASC
        LIMIT %s
    """
    return fetch_all(query, (run_id, limit))


def get_replay_failure_samples(run_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Return persisted row-level replay failures instead of treating them as success."""
    return fetch_all(
        """
        SELECT hrr.*, r.raw_address_text
        FROM historical_replay_result hrr
        JOIN raw_address_record r
          ON hrr.workspace_name = r.workspace_name
         AND hrr.raw_id = r.raw_id
        WHERE hrr.run_id = %s AND hrr.processing_status = 'failed'
        ORDER BY hrr.replay_result_id ASC
        LIMIT %s
        """,
        (run_id, limit),
    )
