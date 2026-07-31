from __future__ import annotations

import json
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
from addressforge.core.utils import logger, ttl_cache
from addressforge.models.runtime_manifest import (
    resolve_runtime_manifest,
    summarize_validation_failure,
    validate_runtime_manifest,
)


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


_MODEL_LIFECYCLE_ORDER = {
    "draft": 0,
    "trained": 10,
    "evaluated": 20,
    "promoted": 30,
    "deprecated": 40,
}


def _forward_only_lifecycle_status(
    existing_status: str | None,
    requested_status: str | None,
) -> str | None:
    """
    Ordinary artifact/metric registration may advance lifecycle state, but it
    must never demote a promoted or deprecated immutable version.
    """
    if requested_status is None:
        return existing_status
    existing = str(existing_status or "").strip().lower()
    requested = str(requested_status).strip().lower()
    if existing not in _MODEL_LIFECYCLE_ORDER:
        return requested
    if requested not in _MODEL_LIFECYCLE_ORDER:
        return requested
    if _MODEL_LIFECYCLE_ORDER[requested] < _MODEL_LIFECYCLE_ORDER[existing]:
        return existing
    return requested


@ttl_cache(seconds=600)
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
        "status": _forward_only_lifecycle_status(
            existing.get("status") if existing else None,
            status,
        ),
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


def _find_registry_model(
    *,
    workspace_name: str,
    model_id: int | None,
    model_name: str | None,
    model_version: str | None,
) -> dict[str, Any] | None:
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
    return _first_or_none(rows)


def build_release_readiness_report(
    target: dict[str, Any],
    *,
    bypass_for_bootstrap: bool = False,
) -> dict[str, Any]:
    """Build a complete, read-only release readiness report for one immutable version."""
    checks: list[dict[str, Any]] = []

    def add_check(
        code: str,
        passed: bool,
        message: str,
        **evidence: Any,
    ) -> None:
        checks.append(
            {
                "code": code,
                "passed": bool(passed),
                "message": message,
                **evidence,
            }
        )

    identity = {
        "model_id": target.get("model_id"),
        "workspace_name": target.get("workspace_name"),
        "model_name": target.get("model_name"),
        "model_version": target.get("model_version"),
    }
    if bypass_for_bootstrap:
        return {
            "status": "ready",
            "ready": True,
            "reason": "Release Gate bypassed for explicit registry bootstrap.",
            "target": identity,
            "checks": [
                {
                    "code": "explicit_bootstrap_bypass",
                    "passed": True,
                    "message": "Explicit bootstrap bypass requested.",
                }
            ],
            "blockers": [],
            "final_f1": 0.0,
            "bypassed": True,
        }

    try:
        raw_metrics = target.get("metrics_json")
        if isinstance(raw_metrics, dict):
            metrics = raw_metrics
        elif raw_metrics:
            metrics = json.loads(str(raw_metrics))
        else:
            metrics = {}
        metrics_ok = bool(metrics)
        add_check(
            "evaluation_metrics_present",
            metrics_ok,
            (
                "Mandatory evaluation metrics are present."
                if metrics_ok
                else "Mandatory evaluation metrics missing. 缺少强制评测指标。"
            ),
        )

        benchmark = metrics.get("release_benchmark")
        comparison = metrics.get("release_comparison")
        replay_m = metrics.get("replay_metrics")
        assist_readiness = metrics.get("decision_assist_rollout_readiness")
        shadow_m = metrics.get("decision_shadow_assist")

        for name, value in (
            ("release_benchmark", benchmark),
            ("release_comparison", comparison),
            ("replay_metrics", replay_m),
            ("decision_assist_rollout_readiness", assist_readiness),
            ("decision_shadow_assist", shadow_m),
        ):
            add_check(
                f"{name}_present",
                isinstance(value, dict),
                (
                    f"{name} evidence is present."
                    if isinstance(value, dict)
                    else f"Mandatory {name} evidence missing."
                ),
            )

        benchmark = benchmark if isinstance(benchmark, dict) else {}
        comparison = comparison if isinstance(comparison, dict) else {}
        replay_m = replay_m if isinstance(replay_m, dict) else {}
        assist_readiness = (
            assist_readiness if isinstance(assist_readiness, dict) else {}
        )
        shadow_m = shadow_m if isinstance(shadow_m, dict) else {}

        required_benchmark_thresholds = {
            "decision_f1": 0.60,
            "building_type_f1": 0.80,
            "unit_number_f1": 0.80,
            "unit_recall": 0.70,
            "commercial_f1": 0.15,
        }
        required_distribution_caps = {
            "review_rate": 0.35,
            "reject_rate": 0.10,
        }
        final_f1 = 0.0
        for metric_name, threshold in required_benchmark_thresholds.items():
            present = metric_name in benchmark
            value = float(benchmark.get(metric_name, 0.0))
            if metric_name == "decision_f1":
                final_f1 = value
            add_check(
                f"benchmark_{metric_name}",
                present and value >= threshold,
                (
                    f"Accuracy Gate passed: {metric_name}={value}."
                    if present and value >= threshold
                    else f"Accuracy Gate Failed: {metric_name} ({value}) < {threshold}"
                ),
                observed=value,
                minimum=threshold,
            )
        for metric_name, cap in required_distribution_caps.items():
            present = metric_name in benchmark
            value = float(benchmark.get(metric_name, 0.0))
            add_check(
                f"distribution_{metric_name}",
                present and value <= cap,
                (
                    f"Distribution Gate passed: {metric_name}={value}."
                    if present and value <= cap
                    else f"Distribution Gate Failed: {metric_name} ({value}) > {cap}"
                ),
                observed=value,
                maximum=cap,
            )

        comparison_checks = comparison.get("gate_checks")
        comparison_checks = comparison_checks if isinstance(comparison_checks, list) else []
        failed_comparisons = [
            str(item.get("metric") or "unknown")
            for item in comparison_checks
            if isinstance(item, dict) and not bool(item.get("passed"))
        ]
        add_check(
            "candidate_not_worse_than_active",
            bool(comparison.get("active_available"))
            and bool(comparison_checks)
            and not failed_comparisons
            and bool(comparison.get("promote_recommended")),
            (
                "Candidate is not worse than active on required release metrics."
                if comparison_checks
                and not failed_comparisons
                and bool(comparison.get("promote_recommended"))
                else "Candidate vs active Gate Failed: "
                + (
                    ", ".join(failed_comparisons)
                    if failed_comparisons
                    else "complete active comparison is missing"
                )
            ),
            failed_metrics=failed_comparisons,
        )

        risk = float(comparison.get("regression_risk", 1.0))
        add_check(
            "replay_regression_risk",
            risk <= 0.05,
            (
                f"Replay regression risk passed: {risk}."
                if risk <= 0.05
                else f"Stability Gate Failed: Regression Risk ({risk}) > 0.05"
            ),
            observed=risk,
            maximum=0.05,
        )
        failures = int(replay_m.get("failures", 0))
        processed = int(replay_m.get("processed_samples", 0))
        add_check(
            "replay_reliability",
            failures == 0 and processed > 0 and replay_m.get("status") != "failed",
            (
                f"Replay Gate passed with {processed} samples and no failures."
                if failures == 0 and processed > 0 and replay_m.get("status") != "failed"
                else "Replay Gate Failed: no successful replay evidence or unhandled failures detected."
            ),
            processed_samples=processed,
            failures=failures,
            replay_status=replay_m.get("status"),
        )

        assist_status = assist_readiness.get("status")
        assist_checks = assist_readiness.get("checks")
        assist_checks = assist_checks if isinstance(assist_checks, dict) else {}
        failed_assist_checks = [
            name for name, passed in assist_checks.items() if not bool(passed)
        ]
        assist_passed = (
            assist_status == "ready_for_assist_trial"
            and bool(assist_checks)
            and not failed_assist_checks
        )
        add_check(
            "shadow_assist_readiness",
            assist_passed,
            (
                "Shadow/Assist readiness passed."
                if assist_passed
                else (
                    f"Shadow Gate Failed: Sub-checks failed: {', '.join(failed_assist_checks)}"
                    if failed_assist_checks
                    else f"Shadow Gate Failed: Status is {assist_status}, expected ready_for_assist_trial."
                )
            ),
            readiness_status=assist_status,
            failed_checks=failed_assist_checks,
        )

        shadow_advantage = float(shadow_m.get("shadow_advantage", -1.0))
        disagreement_rate = float(shadow_m.get("disagreement_rate", 1.0))
        add_check(
            "shadow_quality",
            shadow_advantage >= 0.0 and disagreement_rate <= 0.15,
            (
                "Shadow quality Gate passed."
                if shadow_advantage >= 0.0 and disagreement_rate <= 0.15
                else "Shadow Gate Failed: shadow_advantage must be >= 0 and disagreement_rate <= 0.15"
            ),
            shadow_advantage=shadow_advantage,
            disagreement_rate=disagreement_rate,
        )

        resolved_manifest = resolve_runtime_manifest(target)
        manifest_validation = validate_runtime_manifest(
            resolved_manifest,
            model_row=target,
            require_hashes=True,
            check_files=True,
        )
        add_check(
            "runtime_manifest",
            manifest_validation.ok,
            (
                "Runtime manifest contract passed."
                if manifest_validation.ok
                else "Consistency Gate Failed: "
                f"{summarize_validation_failure(manifest_validation)}"
            ),
            validation=manifest_validation.to_dict(),
        )
    except Exception as exc:
        logger.error(
            "Release gate error for model %s: %s",
            target.get("model_version"),
            exc,
        )
        add_check("gate_execution", False, f"Gate error: {exc}")
        final_f1 = 0.0

    blockers = [item for item in checks if not item["passed"]]
    return {
        "status": "ready" if not blockers else "blocked",
        "ready": not blockers,
        "reason": (
            "All release gates passed."
            if not blockers
            else str(blockers[0]["message"])
        ),
        "target": identity,
        "checks": checks,
        "blockers": blockers,
        "final_f1": final_f1,
        "bypassed": False,
    }


def model_release_readiness(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    model_id: int | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
) -> dict[str, Any]:
    """Resolve one registry version and return its read-only release report."""
    target = _find_registry_model(
        workspace_name=workspace_name,
        model_id=model_id,
        model_name=model_name,
        model_version=model_version,
    )
    if not target:
        raise ValueError("Model version not found in registry.")
    return build_release_readiness_report(target)


def promote_model(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    model_id: int | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
    notes: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    expected_active_model_id: int | None = None,
) -> dict[str, Any]:
    """
    Promote one immutable model version after a complete, read-only readiness report.
    """
    target = _find_registry_model(
        workspace_name=workspace_name,
        model_id=model_id,
        model_name=model_name,
        model_version=model_version,
    )
    if not target:
        raise ValueError("Model version not found in registry.")

    readiness = build_release_readiness_report(
        target,
        bypass_for_bootstrap=force,
    )
    if dry_run or not readiness["ready"]:
        return readiness
    final_f1 = float(readiness.get("final_f1") or 0.0)

    # --- EXECUTION: Promoting the model ---
    with db_cursor() as (conn, cursor):
        cursor.execute(
            """
            SELECT default_model_id
            FROM workspace_registry
            WHERE workspace_name = %s
            FOR UPDATE
            """,
            (workspace_name,),
        )
        locked_workspace = cursor.fetchone()
        if not locked_workspace:
            conn.rollback()
            return {
                "status": "blocked",
                "ready": False,
                "reason": f"Activation blocked: workspace not found: {workspace_name}",
                "blockers": [
                    {
                        "code": "workspace_missing",
                        "passed": False,
                        "message": f"Workspace not found: {workspace_name}",
                    }
                ],
                "readiness": readiness,
            }
        current_model_id = locked_workspace.get("default_model_id")
        if (
            expected_active_model_id is not None
            and current_model_id != expected_active_model_id
        ):
            conn.rollback()
            return {
                "status": "blocked",
                "ready": False,
                "reason": (
                    "Activation compare-and-swap failed: active model changed "
                    f"from expected {expected_active_model_id} to {current_model_id}."
                ),
                "blockers": [
                    {
                        "code": "active_model_changed",
                        "passed": False,
                        "message": "Active model changed after readiness evaluation.",
                        "expected_active_model_id": expected_active_model_id,
                        "current_active_model_id": current_model_id,
                    }
                ],
                "readiness": readiness,
            }
        # Reset defaults for this workspace
        cursor.execute("UPDATE model_registry SET is_default = 0 WHERE workspace_name = %s", (workspace_name,))
        # Promote candidate
        cursor.execute(
            """
            UPDATE model_registry
            SET is_default = 1, status = 'promoted', promoted_at = NOW(), notes = COALESCE(%s, notes)
            WHERE model_id = %s AND workspace_name = %s
            """,
            (
                notes or f"Promoted via hardened Release Gate. F1={final_f1}",
                target["model_id"],
                workspace_name,
            ),
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
        
    # Invalidate Caches
    # 使缓存失效
    try:
        get_active_model.clear_cache()
        get_workspace.clear_cache()
    except Exception:
        pass
        
    logger.info("Hardened Release Gate passed for model %s", target["model_version"])
    return {
        "status": "promoted",
        "model_id": target["model_id"],
        "final_f1": final_f1,
        "previous_model_id": current_model_id,
        "readiness": readiness,
    }




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
    # Use force=True for bootstrapping
    promoted = promote_model(workspace_name=workspace_name, model_id=record["model_id"], notes="bootstrap default model", force=True)
    workspace = ensure_default_workspace()
    if workspace.get("default_model_id") != promoted.get("model_id"):
        with db_cursor() as (conn, cursor):
            cursor.execute(
                "UPDATE workspace_registry SET default_model_id = %s WHERE workspace_name = %s",
                (promoted["model_id"], workspace_name),
            )
            conn.commit()
    return promoted


def rollback_model(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    notes: str | None = None,
    *,
    target_model_id: int | None = None,
    expected_active_model_id: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Roll back transactionally to one explicit immutable, contract-valid version.
    """
    active = get_active_model(workspace_name)
    active_id = int(active["model_id"]) if active and active.get("model_id") is not None else None
    expected_id = (
        expected_active_model_id
        if expected_active_model_id is not None
        else active_id
    )

    if target_model_id is not None:
        target_rows = fetch_all(
            """
            SELECT *
            FROM model_registry
            WHERE workspace_name = %s
              AND model_id = %s
              AND status IN ('promoted', 'deprecated')
            LIMIT 1
            """,
            (workspace_name, target_model_id),
        )
    else:
        target_rows = fetch_all(
            """
            SELECT *
            FROM model_registry
            WHERE workspace_name = %s
              AND status IN ('promoted', 'deprecated')
              AND (model_id != %s OR %s IS NULL)
            ORDER BY promoted_at DESC
            LIMIT 1
            """,
            (workspace_name, active_id, active_id),
        )
    target = _first_or_none(target_rows)
    if not target:
        raise ValueError("No previous model found for rollback. 找不到可用于回滚的先前模型。")

    manifest_validation = validate_runtime_manifest(
        resolve_runtime_manifest(target),
        model_row=target,
        require_hashes=True,
        check_files=True,
    )
    rollback_readiness = {
        "status": "ready" if manifest_validation.ok else "blocked",
        "ready": manifest_validation.ok,
        "target_model_id": target.get("model_id"),
        "current_active_model_id": active_id,
        "runtime_manifest_validation": manifest_validation.to_dict(),
        "reason": (
            "Rollback target runtime contract passed."
            if manifest_validation.ok
            else "Rollback blocked by runtime contract: "
            f"{summarize_validation_failure(manifest_validation)}"
        ),
    }
    if dry_run or not manifest_validation.ok:
        return rollback_readiness

    with db_cursor() as (conn, cursor):
        cursor.execute(
            """
            SELECT default_model_id
            FROM workspace_registry
            WHERE workspace_name = %s
            FOR UPDATE
            """,
            (workspace_name,),
        )
        locked_workspace = cursor.fetchone()
        current_locked_id = (
            locked_workspace.get("default_model_id")
            if locked_workspace
            else None
        )
        if not locked_workspace or current_locked_id != expected_id:
            conn.rollback()
            return {
                "status": "blocked",
                "ready": False,
                "reason": (
                    "Rollback compare-and-swap failed: active model changed "
                    f"from expected {expected_id} to {current_locked_id}."
                ),
                "target_model_id": target.get("model_id"),
                "current_active_model_id": current_locked_id,
            }

        cursor.execute(
            """
            UPDATE model_registry
            SET is_default = 0,
                status = CASE WHEN model_id = %s THEN 'deprecated' ELSE status END
            WHERE workspace_name = %s
            """,
            (active_id, workspace_name),
        )
        cursor.execute(
            """
            UPDATE model_registry
            SET is_default = 1,
                status = 'promoted',
                promoted_at = NOW(),
                notes = COALESCE(%s, notes)
            WHERE workspace_name = %s AND model_id = %s
            """,
            (
                notes or f"Rolled back from model_id={active_id}.",
                workspace_name,
                target["model_id"],
            ),
        )
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

    try:
        get_active_model.clear_cache()
        get_workspace.clear_cache()
    except Exception:
        pass
    return {
        "status": "rolled_back",
        "model_id": target["model_id"],
        "previous_model_id": active_id,
        "readiness": rollback_readiness,
    }


@ttl_cache(seconds=60)
def get_active_model(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME) -> dict[str, Any] | None:
    workspace = get_workspace(workspace_name)
    if not workspace:
        return None

    pointer_model_id = workspace.get("default_model_id")
    if pointer_model_id is not None:
        rows = fetch_all(
            """
            SELECT *
            FROM model_registry
            WHERE workspace_name = %s AND model_id = %s
            LIMIT 1
            """,
            (workspace_name, pointer_model_id),
        )
        target = _first_or_none(rows)
        if not target:
            logger.error(
                "Workspace %s points to missing model_id=%s; active resolution failed closed.",
                workspace_name,
                pointer_model_id,
            )
            return None
        return {
            **target,
            "_active_source": "workspace_default_model_id",
            "_registry_consistency": {
                "workspace_pointer_matches": True,
                "is_default_matches": int(target.get("is_default") or 0) == 1,
                "status_matches": str(target.get("status") or "") == "promoted",
            },
        }

    # Compatibility bridge for workspaces created before default_model_id.
    # A unique default flag is accepted and reported; arbitrary "latest model"
    # fallback is intentionally forbidden.
    rows = fetch_all(
        """
        SELECT *
        FROM model_registry
        WHERE workspace_name = %s AND is_default = 1
        ORDER BY promoted_at DESC, updated_at DESC, created_at DESC
        LIMIT 2
        """,
        (workspace_name,),
    )
    if len(rows) != 1:
        if rows:
            logger.error(
                "Workspace %s has multiple is_default models and no pointer; active resolution failed closed.",
                workspace_name,
            )
        return None
    return {
        **rows[0],
        "_active_source": "legacy_unique_is_default",
        "_registry_consistency": {
            "workspace_pointer_matches": False,
            "is_default_matches": True,
            "status_matches": str(rows[0].get("status") or "") == "promoted",
        },
    }


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
        # Use force=True for bootstrapping to avoid being blocked by Release Gate
        # 在引导期间使用 force=True，以避免被发布准入拦截
        model = promote_model(
            workspace_name=workspace["workspace_name"],
            model_id=model["model_id"],
            notes="bootstrap default model",
            force=True,
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
