from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Iterable

from addressforge.core.common import create_run, db_cursor, fetch_all, finish_run, dumps_payload, canonicalize_unit_number, normalize_street_name
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.models import get_active_model

logger = logging.getLogger(__name__)

def _json_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        data = json.loads(str(value))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

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
        
    metrics_json = _json_dict(model_row.get("metrics_json"))
    artifact_path = model_row.get("artifact_path")
    artifact_payload: dict[str, Any] = {}
    if artifact_path:
        artifact_file = Path(str(artifact_path))
        try:
            if artifact_file.exists():
                with open(artifact_file, "r", encoding="utf-8") as handle:
                    artifact_payload = json.load(handle)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load model artifact for runtime %s: %s", model_version, exc)
            
    runtime_binding = metrics_json.get("runtime_binding") if isinstance(metrics_json.get("runtime_binding"), dict) else {}
    profile = (
        runtime_binding.get("profile")
        or artifact_payload.get("profile")
        or model_row.get("default_profile")
        or "base_canada"
    )
    parsers = tuple(
        runtime_binding.get("parsers")
        or artifact_payload.get("parsers")
        or ("simple_rule", "hybrid_canada", "libpostal")
    )
    decision_policy = (
        runtime_binding.get("decision_policy")
        if isinstance(runtime_binding.get("decision_policy"), dict)
        else artifact_payload.get("decision_policy")
        if isinstance(artifact_payload.get("decision_policy"), dict)
        else {}
    )
    
    # Extract manifests for sub-services
    # 提取子服务的清单
    decision_model_artifact = (
        metrics_json.get("decision_model_artifact")
        if isinstance(metrics_json.get("decision_model_artifact"), dict)
        else artifact_payload.get("decision_model_artifact")
        if isinstance(artifact_payload.get("decision_model_artifact"), dict)
        else {}
    )
    
    reranker_model_artifact = (
        metrics_json.get("reranker_model_artifact")
        if isinstance(metrics_json.get("reranker_model_artifact"), dict)
        else artifact_payload.get("reranker_model_artifact")
        if isinstance(artifact_payload.get("reranker_model_artifact"), dict)
        else {}
    )
    
    building_type_model_artifact = (
        metrics_json.get("building_type_model_artifact")
        if isinstance(metrics_json.get("building_type_model_artifact"), dict)
        else artifact_payload.get("building_type_model_artifact")
        if isinstance(artifact_payload.get("building_type_model_artifact"), dict)
        else {}
    )
    
    # Build a unified manifest for constructors
    # 为构造函数构建统一的清单
    full_manifest = {
        **artifact_payload,
        "decision_model_artifact": decision_model_artifact,
        "reranker_model_artifact": reranker_model_artifact,
        "building_type_model_artifact": building_type_model_artifact
    }

    from addressforge.services.model_service import build_model_service_from_manifest
    from addressforge.services.reranker_service import build_reranker_service_from_manifest
    
    return {
        "ok": True,
        "profile": profile,
        "parsers": parsers,
        "decision_policy": decision_policy,
        "model_service": build_model_service_from_manifest(full_manifest),
        "reranker_service": build_reranker_service_from_manifest(full_manifest),
        "manifest": full_manifest
    }

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
            reranker_service=candidate_runtime["reranker_service"]
        )
        active_service = AddressPlatformService(
            default_profile=active_runtime["profile"],
            default_parsers=active_runtime["parsers"],
            decision_policy=active_runtime["decision_policy"],
            model_service=active_runtime["model_service"],
            reranker_service=active_runtime["reranker_service"]
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
        
        mismatches = []
        
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
                cand_un = cand_res.get("suggested_unit_number")
                
                act_dec = act_res.get("decision")
                act_bt = act_res.get("building_type")
                act_un = act_res.get("suggested_unit_number")
                
                is_diff = (cand_dec != act_dec or cand_bt != act_bt or cand_un != act_un)
                if is_diff:
                    candidate_vs_active_diffs += 1
                    if len(mismatches) < 50:
                        mismatches.append({
                            "raw_id": raw_id,
                            "raw_text": raw_text,
                            "candidate": {"decision": cand_dec, "building_type": cand_bt, "unit_number": cand_un},
                            "active": {"decision": act_dec, "building_type": act_bt, "unit_number": act_un},
                            "current": {"decision": current_dec, "building_type": current_bt, "unit_number": current_un}
                        })
                
                decision_matches += int(cand_dec == act_dec)
                building_type_matches += int(cand_bt == act_bt)
                unit_number_matches += int(cand_un == act_un)
                
                active_current_matches += int(act_dec == current_dec)
                candidate_current_matches += int(cand_dec == current_dec)
                
                total_processed += 1
                
            except Exception as e:
                logger.error("Replay failure on raw_id %d: %s", raw_id, e)
                failures += 1
                
        # 3. Finalize and Save Metrics
        # 3. 完成并保存指标
        consistency_score = round(decision_matches / total_processed, 4) if total_processed > 0 else 1.0
        decision_match_rate = round(decision_matches / total_processed, 4) if total_processed > 0 else 0.0
        building_type_match_rate = round(building_type_matches / total_processed, 4) if total_processed > 0 else 0.0
        unit_number_match_rate = round(unit_number_matches / total_processed, 4) if total_processed > 0 else 0.0
        disagreement_rate = round(candidate_vs_active_diffs / total_processed, 4) if total_processed > 0 else 0.0
        
        active_current_match_rate = round(active_current_matches / total_processed, 4) if total_processed > 0 else 0.0
        candidate_current_match_rate = round(candidate_current_matches / total_processed, 4) if total_processed > 0 else 0.0
        
        replay_id = 0
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
                    workspace_name, run_id, 
                    (candidate_model or {}).get("model_name", "candidate"),
                    candidate_version,
                    total_processed, decision_match_rate, building_type_match_rate, unit_number_match_rate,
                ),
            )
            replay_id = cursor.lastrowid
            conn.commit()
        
        # Add runtime identity for transparency
        # 添加运行时标识以提高透明度
        runtime_identity = {
            "candidate": {
                "decision_model": candidate_runtime["model_service"].describe_runtime(),
                "reranker_model": candidate_runtime["reranker_service"].describe_runtime(),
                "profile": candidate_runtime["profile"],
                "parsers": list(candidate_runtime["parsers"]),
            },
            "active": {
                "decision_model": active_runtime["model_service"].describe_runtime(),
                "reranker_model": active_runtime["reranker_service"].describe_runtime(),
                "profile": active_runtime["profile"],
                "parsers": list(active_runtime["parsers"]),
            }
        }

        metadata = {
            "replay_id": replay_id,
            "processed_count": total_processed,
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
            "active_model_version": (active_model or {}).get("model_version"),
            "candidate_version": candidate_version,
            "runtime_identity": runtime_identity
        }
    except Exception as exc:
        logger.exception("Historical replay failed: %s", exc)
        finish_run(run_id, "failed", notes=str(exc))
        raise
