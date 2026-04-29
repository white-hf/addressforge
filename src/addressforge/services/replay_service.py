from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Dict
from addressforge.core.common import create_run, db_cursor, fetch_all, finish_run, dumps_payload
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.core.utils import logger
from addressforge.models import get_active_model

def _load_model_runtime(workspace_name: str, model_version: str) -> Any:
    """
    Internal helper to load a model version into memory for runtime inference.
    用于将模型版本加载到内存中进行运行时推理的内部辅助函数。
    """
    logger.info("Loading model runtime: %s", model_version)
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
        return (False, None, None, None)
    artifact_path = model_row.get("artifact_path")
    artifact_payload: dict[str, Any] = {}
    if artifact_path:
        artifact_file = Path(str(artifact_path))
        if not artifact_file.exists():
            artifact_file = None
        try:
            if artifact_file is not None:
                with open(artifact_file, "r", encoding="utf-8") as handle:
                    artifact_payload = json.load(handle)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load model artifact for runtime %s: %s", model_version, exc)
    profile = artifact_payload.get("profile") or model_row.get("default_profile") or "base_canada"
    parsers = tuple(artifact_payload.get("parsers") or ("simple_rule", "hybrid_canada", "libpostal"))
    decision_policy = artifact_payload.get("decision_policy") if isinstance(artifact_payload.get("decision_policy"), dict) else {}
    return (True, profile, parsers, decision_policy)

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
        if not candidate_runtime[0]:
            raise ValueError(f"candidate runtime unavailable: {workspace_name}/{candidate_version}")
        if not active_runtime[0]:
            raise ValueError(f"active runtime unavailable: {workspace_name}")
        candidate_service = AddressPlatformService(
            default_profile=candidate_runtime[1],
            default_parsers=candidate_runtime[2],
            decision_policy=candidate_runtime[3],
        )
        active_service = AddressPlatformService(
            default_profile=active_runtime[1],
            default_parsers=active_runtime[2],
            decision_policy=active_runtime[3],
        )

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
            WHERE r.workspace_name = %s AND r.is_active = 1
            ORDER BY r.raw_id DESC
            LIMIT %s
        """
        records = fetch_all(query, (workspace_name, limit))
        
        if not records:
            return {"status": "success", "processed": 0, "run_id": run_id}

        mismatches = 0
        failures = 0
        decision_matches = 0
        building_matches = 0
        unit_matches = 0
        active_matches_current = 0
        candidate_matches_current = 0
        
        with db_cursor() as (conn, cursor):
            for row in records:
                req = AddressRequest(
                    raw_address_text=row["raw_address_text"],
                    city=row["city"],
                    province=row["province"],
                    postal_code=row["postal_code"]
                )
                
                try:
                    active_res = active_service.validate(
                        req.model_copy(update={"profile": active_runtime[1], "parsers": list(active_runtime[2]) if active_runtime[2] else None})
                    )
                    candidate_res = candidate_service.validate(
                        req.model_copy(update={"profile": candidate_runtime[1], "parsers": list(candidate_runtime[2]) if candidate_runtime[2] else None})
                    )

                    active_dec = active_res.get("decision")
                    active_bt = active_res.get("building_type")
                    active_unit = active_res.get("suggested_unit_number")
                    candidate_dec = candidate_res.get("decision")
                    candidate_bt = candidate_res.get("building_type")
                    candidate_unit = candidate_res.get("suggested_unit_number")
                    current_dec = row.get("current_decision")
                    current_bt = row.get("current_building_type")
                    current_unit = row.get("current_unit_number")

                    decision_match = int((active_dec or "") == (candidate_dec or ""))
                    building_match = int((active_bt or "") == (candidate_bt or ""))
                    unit_match = int((active_unit or "") == (candidate_unit or ""))
                    is_different = 1 if (active_dec, active_bt, active_unit) != (candidate_dec, candidate_bt, candidate_unit) else 0
                    decision_matches += decision_match
                    building_matches += building_match
                    unit_matches += unit_match
                    if is_different:
                        mismatches += 1
                    if (active_dec or "", active_bt or "", active_unit or "") == (current_dec or "", current_bt or "", current_unit or ""):
                        active_matches_current += 1
                    if (candidate_dec or "", candidate_bt or "", candidate_unit or "") == (current_dec or "", current_bt or "", current_unit or ""):
                        candidate_matches_current += 1
                        
                    # 4. Persist detailed results
                    # 4. 持久化详细结果
                    cursor.execute(
                        """
                        INSERT INTO historical_replay_result (
                            workspace_name, run_id, raw_id, 
                            current_decision, current_building_type, current_unit_number,
                            active_decision, active_building_type, active_unit_number,
                            candidate_decision, candidate_building_type, candidate_unit_number,
                            decision_match, building_type_match, unit_number_match, candidate_vs_active_different
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) AS new_row
                        ON DUPLICATE KEY UPDATE
                            current_decision = new_row.current_decision,
                            current_building_type = new_row.current_building_type,
                            current_unit_number = new_row.current_unit_number,
                            active_decision = new_row.active_decision,
                            active_building_type = new_row.active_building_type,
                            active_unit_number = new_row.active_unit_number,
                            candidate_decision = new_row.candidate_decision,
                            candidate_building_type = new_row.candidate_building_type,
                            candidate_unit_number = new_row.candidate_unit_number,
                            decision_match = new_row.decision_match,
                            building_type_match = new_row.building_type_match,
                            unit_number_match = new_row.unit_number_match,
                            candidate_vs_active_different = new_row.candidate_vs_active_different
                        """,
                        (
                            workspace_name, run_id, row["raw_id"],
                            current_dec, current_bt, current_unit,
                            active_dec, active_bt, active_unit,
                            candidate_dec, candidate_bt, candidate_unit,
                            decision_match,
                            building_match,
                            unit_match,
                            is_different,
                        )
                    )
                except Exception as e:
                    logger.error("Inference failure during replay for raw_id %s: %s", row["raw_id"], e)
                    failures += 1
            
            conn.commit()

        # 5. Summary Metrics
        # 5. 汇总指标
        total_processed = len(records) - failures
        consistency_score = round((total_processed - mismatches) / total_processed, 4) if total_processed > 0 else 0.0
        decision_match_rate = round(decision_matches / total_processed, 4) if total_processed > 0 else 0.0
        building_type_match_rate = round(building_matches / total_processed, 4) if total_processed > 0 else 0.0
        unit_number_match_rate = round(unit_matches / total_processed, 4) if total_processed > 0 else 0.0
        disagreement_rate = round(mismatches / total_processed, 4) if total_processed > 0 else 0.0
        active_current_match_rate = round(active_matches_current / total_processed, 4) if total_processed > 0 else 0.0
        candidate_current_match_rate = round(candidate_matches_current / total_processed, 4) if total_processed > 0 else 0.0

        with db_cursor() as (conn, cursor):
            cursor.execute(
                """
                INSERT INTO historical_replay_run (
                    workspace_name, run_id, model_name, model_version,
                    processed_count, decision_match_rate, building_type_match_rate, unit_number_match_rate
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) AS new_run
                ON DUPLICATE KEY UPDATE
                    model_name = new_run.model_name,
                    model_version = new_run.model_version,
                    processed_count = new_run.processed_count,
                    decision_match_rate = new_run.decision_match_rate,
                    building_type_match_rate = new_run.building_type_match_rate,
                    unit_number_match_rate = new_run.unit_number_match_rate
                """,
                (
                    workspace_name,
                    run_id,
                    (candidate_model or active_model or {}).get("model_name") or "candidate_model",
                    candidate_version or (active_model or {}).get("model_version") or "active",
                    total_processed,
                    decision_match_rate,
                    building_type_match_rate,
                    unit_number_match_rate,
                ),
            )
            conn.commit()
        
        metadata = {
            "total_samples": len(records),
            "processed": total_processed,
            "failures": failures,
            "mismatches": mismatches,
            "consistency_score": consistency_score,
            "decision_match_rate": decision_match_rate,
            "building_type_match_rate": building_type_match_rate,
            "unit_number_match_rate": unit_number_match_rate,
            "disagreement_rate": disagreement_rate,
            "active_current_match_rate": active_current_match_rate,
            "candidate_current_match_rate": candidate_current_match_rate,
            "active_model_version": (active_model or {}).get("model_version"),
            "candidate_version": candidate_version,
        }
        
        finish_run(run_id, "completed", notes=dumps_payload(metadata))
        logger.info("True Replay finished. Consistency: %f, Failures: %d", consistency_score, failures)
        
        return {
            "status": "success",
            "run_id": run_id,
            "processed": total_processed,
            "consistency_score": consistency_score,
            "decision_match_rate": decision_match_rate,
            "building_type_match_rate": building_type_match_rate,
            "unit_number_match_rate": unit_number_match_rate,
            "disagreement_rate": disagreement_rate,
            "active_current_match_rate": active_current_match_rate,
            "candidate_current_match_rate": candidate_current_match_rate,
            "mismatches": mismatches,
            "failures": failures,
        }

    except Exception as exc:
        logger.exception("True Replay pipeline crashed: %s", exc)
        finish_run(run_id, "failed", notes=str(exc))
        raise

def get_release_readiness_report(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME) -> dict[str, Any]:
    """
    Generates a summarized report comparing the candidate model against the active one.
    生成候选模型与当前活跃模型的对比摘要报告。
    """
    latest_eval = fetch_all(
        """
        SELECT metrics_json, created_at 
        FROM model_registry 
        WHERE workspace_name = %s AND status = 'evaluated'
        ORDER BY created_at DESC LIMIT 1
        """,
        (workspace_name,)
    )
    
    if not latest_eval:
        return {"ready": False, "reason": "No evaluation data found"}
        
    metrics = json.loads(latest_eval[0]["metrics_json"] or "{}")
    comparison = metrics.get("release_comparison", {}) if isinstance(metrics, dict) else {}
    benchmark = metrics.get("release_benchmark", {}) if isinstance(metrics, dict) else {}
    replay = metrics.get("replay_metrics", {}) if isinstance(metrics, dict) else {}
    shadow = metrics.get("shadow", {}) if isinstance(metrics, dict) else {}
    is_ready = (
        float(benchmark.get("decision_f1", 0.0)) >= 0.90
        and float(benchmark.get("building_type_f1", 0.0)) >= 0.85
        and float(benchmark.get("unit_number_f1", 0.0)) >= 0.85
        and float(benchmark.get("unit_recall", 0.0)) >= 0.85
        and float(benchmark.get("commercial_f1", 0.0)) >= 0.85
        and float(benchmark.get("review_rate", 1.0)) <= 0.35
        and float(benchmark.get("reject_rate", 1.0)) <= 0.10
        and float(comparison.get("regression_risk", 1.0)) <= 0.02
        and int(replay.get("failures", 1)) == 0
        and bool(shadow.get("promote_recommended"))
        and float(shadow.get("shadow_advantage", -1.0)) >= 0.0
        and float(shadow.get("disagreement_rate", 1.0)) <= 0.10
    )
    
    return {
        "ready": is_ready,
        "metrics": benchmark,
        "gate_checks": comparison.get("gate_checks", []),
        "timestamp": latest_eval[0].get("created_at")
    }

def get_mismatch_samples(run_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Retrieves detailed samples where candidate and active models disagreed.
    检索候选模型与活动模型不一致的详细样本。
    """
    query = """
        SELECT hrr.*, r.raw_address_text
        FROM historical_replay_result hrr
        JOIN raw_address_record r ON hrr.raw_id = r.raw_id
        WHERE hrr.run_id = %s AND hrr.candidate_vs_active_different = 1
        LIMIT %s
    """
    return fetch_all(query, (run_id, limit))
