from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from addressforge.core.common import db_cursor, dumps_payload, fetch_all
from addressforge.core.config import (
    ADDRESSFORGE_DEFAULT_PROFILE,
    ADDRESSFORGE_MODEL_ARTIFACT_DIR,
    ADDRESSFORGE_MODEL_FAMILY,
    ADDRESSFORGE_MODEL_NAME,
    ADDRESSFORGE_MODEL_VERSION,
    ADDRESSFORGE_REFERENCE_VERSION,
    ADDRESSFORGE_WORKSPACE_NAME,
)
from addressforge.core.utils import logger


@dataclass(frozen=True)
class WorkspaceRecord:
    workspace_id: int
    workspace_name: str
    description: str | None
    default_model_id: int | None
    default_profile: str
    default_reference_version: str | None
    default_language: str
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class ModelRecord:
    model_id: int
    workspace_name: str
    model_name: str
    model_version: str
    model_family: str
    status: str
    is_default: int
    default_profile: str
    dataset_name: str | None
    training_run_id: int | None
    evaluation_run_id: int | None
    reference_version: str | None
    rule_version: str | None
    artifact_path: str | None
    metrics_json: str | None
    notes: str | None
    created_at: str | None = None
    updated_at: str | None = None
    promoted_at: str | None = None


def _first_or_none(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return rows[0] if rows else None


def get_workspace(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME) -> dict[str, Any] | None:
    return _first_or_none(
        fetch_all("SELECT * FROM workspace_registry WHERE workspace_name = %s LIMIT 1", (workspace_name,))
    )


def ensure_workspace(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    description: str | None = None,
    default_profile: str | None = None,
    default_reference_version: str | None = None,
    default_language: str | None = None,
) -> dict[str, Any]:
    existing = get_workspace(workspace_name)
    if existing:
        updates: list[str] = []
        params: list[Any] = []
        if description is not None and description != existing.get("description"):
            updates.append("description = %s")
            params.append(description)
        if default_profile is not None and default_profile != existing.get("default_profile"):
            updates.append("default_profile = %s")
            params.append(default_profile)
        if default_reference_version is not None and default_reference_version != existing.get("default_reference_version"):
            updates.append("default_reference_version = %s")
            params.append(default_reference_version)
        if default_language is not None and default_language != existing.get("default_language"):
            updates.append("default_language = %s")
            params.append(default_language)
        if updates:
            params.append(workspace_name)
            with db_cursor() as (conn, cursor):
                cursor.execute(
                    f"UPDATE workspace_registry SET {', '.join(updates)} WHERE workspace_name = %s",
                    params,
                )
                conn.commit()
            return get_workspace(workspace_name) or existing
        return existing

    with db_cursor() as (conn, cursor):
        cursor.execute(
            """
            INSERT INTO workspace_registry (
                workspace_name, description, default_profile, default_reference_version, default_language
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                workspace_name,
                description,
                default_profile or ADDRESSFORGE_DEFAULT_PROFILE,
                default_reference_version or ADDRESSFORGE_REFERENCE_VERSION,
                default_language or "en",
            ),
        )
        conn.commit()
    return get_workspace(workspace_name) or {}


def ensure_default_workspace() -> dict[str, Any]:
    return ensure_workspace(
        workspace_name=ADDRESSFORGE_WORKSPACE_NAME,
        default_profile=ADDRESSFORGE_DEFAULT_PROFILE,
        default_reference_version=ADDRESSFORGE_REFERENCE_VERSION,
        default_language="en",
    )


def list_workspaces() -> list[dict[str, Any]]:
    return fetch_all("SELECT * FROM workspace_registry ORDER BY workspace_name ASC, created_at DESC")


def get_model(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    model_name: str = ADDRESSFORGE_MODEL_NAME,
    model_version: str = ADDRESSFORGE_MODEL_VERSION,
) -> dict[str, Any] | None:
    return _first_or_none(
        fetch_all(
            """
            SELECT *
            FROM model_registry
            WHERE workspace_name = %s AND model_name = %s AND model_version = %s
            LIMIT 1
            """,
            (workspace_name, model_name, model_version),
        )
    )


def list_models(workspace_name: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM model_registry"
    params: tuple[Any, ...] = ()
    if workspace_name:
        query += " WHERE workspace_name = %s"
        params = (workspace_name,)
    query += " ORDER BY is_default DESC, promoted_at DESC, updated_at DESC, created_at DESC"
    return fetch_all(query, params)


def register_model_version(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    model_name: str = ADDRESSFORGE_MODEL_NAME,
    model_version: str = ADDRESSFORGE_MODEL_VERSION,
    model_family: str = ADDRESSFORGE_MODEL_FAMILY,
    status: str = "trained",
    default_profile: str | None = None,
    dataset_name: str | None = None,
    training_run_id: int | None = None,
    evaluation_run_id: int | None = None,
    reference_version: str | None = None,
    rule_version: str | None = None,
    artifact_path: str | None = None,
    metrics_json: dict[str, Any] | None = None,
    notes: str | None = None,
    is_default: int | None = None,
) -> dict[str, Any]:
    workspace = ensure_workspace(workspace_name)
    existing = get_model(workspace_name, model_name, model_version)
    payload = {
        "model_family": model_family,
        "status": status,
        "default_profile": default_profile or workspace.get("default_profile") or ADDRESSFORGE_DEFAULT_PROFILE,
        "dataset_name": dataset_name,
        "training_run_id": training_run_id,
        "evaluation_run_id": evaluation_run_id,
        "reference_version": reference_version or workspace.get("default_reference_version") or ADDRESSFORGE_REFERENCE_VERSION,
        "rule_version": rule_version,
        "artifact_path": artifact_path,
        "metrics_json": dumps_payload(metrics_json) if metrics_json is not None else None,
        "notes": notes,
    }

    if existing:
        updates = []
        params: list[Any] = []
        for column, value in payload.items():
            if value is None:
                continue
            updates.append(f"{column} = %s")
            params.append(value)
        if is_default is not None:
            updates.append("is_default = %s")
            params.append(int(bool(is_default)))
        if updates:
            params.extend([workspace_name, model_name, model_version])
            with db_cursor() as (conn, cursor):
                cursor.execute(
                    f"""
                    UPDATE model_registry
                    SET {', '.join(updates)}
                    WHERE workspace_name = %s AND model_name = %s AND model_version = %s
                    """,
                    params,
                )
                conn.commit()
        return get_model(workspace_name, model_name, model_version) or existing

    with db_cursor() as (conn, cursor):
        cursor.execute(
            """
            INSERT INTO model_registry (
                workspace_name, model_name, model_version, model_family, status, is_default,
                default_profile, dataset_name, training_run_id, evaluation_run_id,
                reference_version, rule_version, artifact_path, metrics_json, notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                workspace_name,
                model_name,
                model_version,
                model_family,
                status,
                int(bool(is_default)) if is_default is not None else 0,
                payload["default_profile"],
                dataset_name,
                training_run_id,
                evaluation_run_id,
                payload["reference_version"],
                rule_version,
                artifact_path,
                payload["metrics_json"],
                notes,
            ),
        )
        conn.commit()
    return get_model(workspace_name, model_name, model_version) or {}


def promote_model(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    model_id: int | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
    notes: str | None = None,
    force: bool = False
) -> dict[str, Any]:
    """
    Promotes a model version to 'active' status while enforcing the consolidated Release Gate.
    将模型版本提升为“活动 (active)”状态，同时强制执行统一的发布准入。
    """
    import json
    if model_id is not None:
        rows = fetch_all(
            "SELECT * FROM model_registry WHERE workspace_name = %s AND model_id = %s LIMIT 1",
            (workspace_name, model_id),
        )
    else:
        rows = fetch_all(
            """
            SELECT *
            FROM model_registry
            WHERE workspace_name = %s
              AND model_name = COALESCE(%s, model_name)
              AND model_version = COALESCE(%s, model_version)
            ORDER BY promoted_at DESC, updated_at DESC, created_at DESC
            LIMIT 1
            """,
            (workspace_name, model_name, model_version),
        )
    target = _first_or_none(rows)
    if not target:
        raise ValueError("Model version not found in registry.")
    
    # --- HARD RELEASE GATE (Iteration 12 hardening) ---
    # --- 硬核发布准入 (迭代 12 加固) ---
    final_f1 = 0.0
    if not force:
        try:
            m_str = target.get("metrics_json")
            if not m_str:
                return {"status": "blocked", "reason": "Mandatory evaluation metrics missing. 缺少强制评测指标。"}
            
            metrics = json.loads(m_str)
            benchmark = metrics.get("release_benchmark")
            comparison = metrics.get("release_comparison")
            replay_m = metrics.get("replay_metrics")
            shadow_m = metrics.get("shadow")

            # 1. Existence Check
            # 1. 完整性检查
            if not isinstance(benchmark, dict) or not isinstance(comparison, dict) or not isinstance(replay_m, dict):
                return {"status": "blocked", "reason": "Incomplete Release Gate data (benchmark/comparison/replay missing). 准入数据不完整。"}
            if not isinstance(shadow_m, dict):
                return {"status": "blocked", "reason": "Mandatory shadow result missing. 缺少 shadow 结果。"}

            required_benchmark_thresholds = {
                "decision_f1": 0.90,
                "building_type_f1": 0.85,
                "unit_number_f1": 0.85,
                "unit_recall": 0.85,
                "commercial_f1": 0.85,
            }
            required_distribution_caps = {
                "review_rate": 0.35,
                "reject_rate": 0.10,
            }
            for metric_name, threshold in required_benchmark_thresholds.items():
                if metric_name not in benchmark:
                    return {"status": "blocked", "reason": f"Missing required benchmark metric: {metric_name}"}
                metric_value = float(benchmark.get(metric_name, 0.0))
                if metric_value < threshold:
                    return {
                        "status": "blocked",
                        "reason": f"Accuracy Gate Failed: {metric_name} ({metric_value}) < {threshold}",
                    }
                if metric_name == "decision_f1":
                    final_f1 = metric_value

            for metric_name, threshold in required_distribution_caps.items():
                if metric_name not in benchmark:
                    return {"status": "blocked", "reason": f"Missing required distribution metric: {metric_name}"}
                metric_value = float(benchmark.get(metric_name, 0.0))
                if metric_value > threshold:
                    return {
                        "status": "blocked",
                        "reason": f"Distribution Gate Failed: {metric_name} ({metric_value}) > {threshold}",
                    }

            # 3. Stability Gate (Replay + Comparison)
            # 3. 稳定性准入 (重放 + 对比)
            risk = float(comparison.get("regression_risk", 1.0))
            if risk > 0.02:
                return {"status": "blocked", "reason": f"Stability Gate Failed: Regression Risk ({risk}) > 0.02"}
            if int(replay_m.get("failures", 0)) > 0:
                return {"status": "blocked", "reason": "Reliability Gate Failed: Unhandled failures detected in replay."}
            if int(replay_m.get("processed_samples", 0)) <= 0:
                return {"status": "blocked", "reason": "Replay Gate Failed: no replay samples processed."}

            # 4. Shadow Gate must pass together with replay
            # 4. Shadow 与 replay 必须同时通过
            if not bool(shadow_m.get("promote_recommended")):
                return {"status": "blocked", "reason": "Shadow Gate Failed: promote_recommended=false"}
            if float(shadow_m.get("shadow_advantage", -1.0)) < 0.0:
                return {"status": "blocked", "reason": "Shadow Gate Failed: shadow_advantage < 0"}
            if float(shadow_m.get("disagreement_rate", 1.0)) > 0.10:
                return {"status": "blocked", "reason": "Shadow Gate Failed: disagreement_rate > 0.10"}

        except Exception as e:
            logger.error("Release gate error for model %s: %s", target.get("model_version"), e)
            return {"status": "blocked", "reason": f"Gate error: {str(e)}"}

    # --- EXECUTION: Promoting the model ---
    with db_cursor() as (conn, cursor):
        # Reset defaults for this workspace
        cursor.execute("UPDATE model_registry SET is_default = 0 WHERE workspace_name = %s", (workspace_name,))
        # Promote candidate
        cursor.execute(
            """
            UPDATE model_registry
            SET is_default = 1, status = 'promoted', promoted_at = NOW(), notes = COALESCE(%s, notes)
            WHERE model_id = %s
            """,
            (notes or f"Promoted via hardened Release Gate. F1={final_f1}", target["model_id"]),
        )
        # Synchronize workspace default
        cursor.execute(
            """
            UPDATE workspace_registry
            SET default_model_id = %s,
                default_profile = %s,
                default_reference_version = %s
            WHERE workspace_name = %s
            """,
            (
                target["model_id"],
                target.get("default_profile") or ADDRESSFORGE_DEFAULT_PROFILE,
                target.get("reference_version") or ADDRESSFORGE_REFERENCE_VERSION,
                workspace_name,
            ),
        )
        conn.commit()
        
    logger.info("Hardened Release Gate passed for model %s", target["model_version"])
    return {"status": "promoted", "model_id": target["model_id"], "final_f1": final_f1}




def deprecate_model(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    model_id: int | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    if model_id is not None:
        rows = fetch_all(
            "SELECT * FROM model_registry WHERE workspace_name = %s AND model_id = %s LIMIT 1",
            (workspace_name, model_id),
        )
    else:
        rows = fetch_all(
            """
            SELECT *
            FROM model_registry
            WHERE workspace_name = %s
              AND model_name = COALESCE(%s, model_name)
              AND model_version = COALESCE(%s, model_version)
            ORDER BY promoted_at DESC, updated_at DESC, created_at DESC
            LIMIT 1
            """,
            (workspace_name, model_name, model_version),
        )
    target = _first_or_none(rows)
    if not target:
        raise ValueError("Model not found for deprecation")
    with db_cursor() as (conn, cursor):
        cursor.execute(
            """
            UPDATE model_registry
            SET status = 'deprecated',
                is_default = 0,
                notes = COALESCE(%s, notes)
            WHERE model_id = %s
            """,
            (notes, target["model_id"]),
        )
        cursor.execute(
            """
            UPDATE workspace_registry
            SET default_model_id = NULL
            WHERE workspace_name = %s AND default_model_id = %s
            """,
            (workspace_name, target["model_id"]),
        )
        conn.commit()
    return get_model(workspace_name, target["model_name"], target["model_version"]) or target


def ensure_default_model(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    model_name: str = ADDRESSFORGE_MODEL_NAME,
    model_version: str = ADDRESSFORGE_MODEL_VERSION,
    model_family: str = ADDRESSFORGE_MODEL_FAMILY,
    default_profile: str | None = None,
    dataset_name: str | None = "default_training_set",
    artifact_path: str | None = None,
) -> dict[str, Any]:
    workspace = ensure_default_workspace()
    existing = get_model(workspace_name, model_name, model_version)
    if existing:
        return existing
    record = register_model_version(
        workspace_name=workspace_name,
        model_name=model_name,
        model_version=model_version,
        model_family=model_family,
        status="promoted",
        default_profile=default_profile or workspace.get("default_profile") or ADDRESSFORGE_DEFAULT_PROFILE,
        dataset_name=dataset_name,
        artifact_path=artifact_path or ADDRESSFORGE_MODEL_ARTIFACT_DIR,
        is_default=1,
        notes=dumps_payload({"seeded": True, "reason": "default model bootstrap"}),
    )
    promoted = promote_model(workspace_name=workspace_name, model_id=record["model_id"], notes="bootstrap default model")
    workspace = ensure_default_workspace()
    if workspace.get("default_model_id") != promoted.get("model_id"):
        with db_cursor() as (conn, cursor):
            cursor.execute(
                "UPDATE workspace_registry SET default_model_id = %s WHERE workspace_name = %s",
                (promoted["model_id"], workspace_name),
            )
            conn.commit()
    return promoted


def get_active_model(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME) -> dict[str, Any] | None:
    rows = fetch_all(
        """
        SELECT *
        FROM model_registry
        WHERE workspace_name = %s AND is_default = 1
        ORDER BY promoted_at DESC, updated_at DESC, created_at DESC
        LIMIT 1
        """,
        (workspace_name,),
    )
    if rows:
        return _first_or_none(rows)
    rows = fetch_all(
        """
        SELECT *
        FROM model_registry
        WHERE workspace_name = %s
        ORDER BY promoted_at DESC, updated_at DESC, created_at DESC
        LIMIT 1
        """,
        (workspace_name,),
    )
    return _first_or_none(rows)


def bootstrap_default_registry() -> dict[str, Any]:
    workspace = ensure_default_workspace()
    model = ensure_default_model(
        workspace_name=workspace["workspace_name"],
        model_name=ADDRESSFORGE_MODEL_NAME,
        model_version=ADDRESSFORGE_MODEL_VERSION,
        model_family=ADDRESSFORGE_MODEL_FAMILY,
        default_profile=workspace.get("default_profile") or ADDRESSFORGE_DEFAULT_PROFILE,
        dataset_name="default_training_set",
        artifact_path=ADDRESSFORGE_MODEL_ARTIFACT_DIR,
    )
    active = get_active_model(workspace["workspace_name"])
    if not active or active.get("model_id") != model.get("model_id"):
        model = promote_model(
            workspace_name=workspace["workspace_name"],
            model_id=model["model_id"],
            notes="bootstrap default model",
        )
    workspace = ensure_default_workspace()
    if workspace.get("default_model_id") != model.get("model_id"):
        with db_cursor() as (conn, cursor):
            cursor.execute(
                "UPDATE workspace_registry SET default_model_id = %s WHERE workspace_name = %s",
                (model["model_id"], workspace["workspace_name"]),
            )
            conn.commit()
    return {"workspace": workspace, "model": model}
