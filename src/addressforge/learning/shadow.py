from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from addressforge.core.common import create_run, dumps_payload, fetch_all, finish_run, normalize_street_name
from addressforge.core.config import ADDRESSFORGE_MODEL_ARTIFACT_DIR, ADDRESSFORGE_WORKSPACE_NAME
from addressforge.models import get_active_model, get_model, register_model_version
from addressforge.services.replay_service import _load_model_runtime

_SHADOW_METRICS = (
    "decision_f1",
    "building_type_f1",
    "unit_number_f1",
    "unit_recall",
    "commercial_f1",
)


def _artifact_dir() -> Path:
    return Path(os.getenv("ADDRESSFORGE_MODEL_ARTIFACT_DIR", ADDRESSFORGE_MODEL_ARTIFACT_DIR)).expanduser()


def _load_release_benchmark(model_row: dict[str, Any] | None) -> dict[str, Any]:
    if not model_row:
        return {}
    try:
        payload = json.loads(model_row.get("metrics_json") or "{}")
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    release_benchmark = payload.get("release_benchmark")
    return release_benchmark if isinstance(release_benchmark, dict) else {}


def _normalized_value(value: Any, *, field: str) -> str | None:
    if value in (None, ""):
        return None
    if field == "street_name":
        return normalize_street_name(str(value))
    return str(value)


def run_baseline_shadow(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    model_name: str = "shadow_model",
    model_version: str = "v1",
    dataset_name: str = "default_training_set",
) -> dict[str, Any]:
    run_id = create_run("ml_shadow", notes=f"shadow {model_name}:{model_version}")
    try:
        from addressforge.api.server import AddressPlatformService, AddressRequest

        candidate_model = get_model(workspace_name, model_name, model_version)
        if not candidate_model:
            raise ValueError(f"candidate model not found: {workspace_name}/{model_name}:{model_version}")
        active_model = get_active_model(workspace_name)
        candidate_runtime = _load_model_runtime(workspace_name, model_version)
        active_runtime = _load_model_runtime(workspace_name, active_model.get("model_version") if active_model else None)
        if not candidate_runtime[0]:
            raise ValueError(f"candidate runtime unavailable: {workspace_name}/{model_version}")
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

        shadow_rows = fetch_all(
            """
            SELECT r.raw_id, r.raw_address_text, r.city, r.province, r.postal_code, r.country_code,
                   c.decision AS current_decision, c.building_type AS current_building_type,
                   c.suggested_unit_number AS current_unit_number
            FROM raw_address_record r
            LEFT JOIN address_cleaning_result c
              ON c.workspace_name = r.workspace_name AND c.raw_id = r.raw_id
            WHERE r.workspace_name = %s
            ORDER BY r.raw_id DESC
            LIMIT 500
            """,
            (workspace_name,),
        )
        candidate_release = _load_release_benchmark(candidate_model)
        active_release = _load_release_benchmark(active_model)

        deltas: dict[str, float] = {}
        for metric_name in _SHADOW_METRICS:
            candidate_value = float(candidate_release.get(metric_name) or 0.0)
            active_value = float(active_release.get(metric_name) or 0.0)
            deltas[metric_name] = round(candidate_value - active_value, 4)

        if deltas:
            score_delta = round(sum(deltas.values()) / len(deltas), 4)
        else:
            score_delta = 0.0
        compared = 0
        candidate_matches = 0
        active_matches = 0
        disagreements = 0
        disagreement_samples: list[dict[str, Any]] = []
        for row in shadow_rows:
            request = AddressRequest(
                raw_address_text=row["raw_address_text"],
                city=row.get("city"),
                province=row.get("province"),
                postal_code=row.get("postal_code"),
                country_code=row.get("country_code") or "CA",
                profile=candidate_runtime[1] or "base_canada",
                parsers=list(candidate_runtime[2]) if candidate_runtime[2] else None,
            )
            candidate_validation = candidate_service.validate(request)
            active_request = request.model_copy(
                update={
                    "profile": active_runtime[1] or request.profile,
                    "parsers": list(active_runtime[2]) if active_runtime[2] else request.parsers,
                }
            )
            active_validation = active_service.validate(active_request)
            current_tuple = (
                _normalized_value(row.get("current_decision"), field="decision"),
                _normalized_value(row.get("current_building_type"), field="building_type"),
                _normalized_value(row.get("current_unit_number"), field="unit_number"),
            )
            candidate_tuple = (
                _normalized_value(candidate_validation.get("decision"), field="decision"),
                _normalized_value(candidate_validation.get("building_type"), field="building_type"),
                _normalized_value(candidate_validation.get("suggested_unit_number"), field="unit_number"),
            )
            active_tuple = (
                _normalized_value(active_validation.get("decision"), field="decision"),
                _normalized_value(active_validation.get("building_type"), field="building_type"),
                _normalized_value(active_validation.get("suggested_unit_number"), field="unit_number"),
            )
            compared += 1
            candidate_matches += int(candidate_tuple == current_tuple)
            active_matches += int(active_tuple == current_tuple)
            if candidate_tuple != active_tuple:
                disagreements += 1
                if len(disagreement_samples) < 50:
                    disagreement_samples.append(
                        {
                            "raw_id": row["raw_id"],
                            "raw_address_text": row["raw_address_text"],
                            "candidate": {
                                "decision": candidate_tuple[0],
                                "building_type": candidate_tuple[1],
                                "unit_number": candidate_tuple[2],
                            },
                            "active": {
                                "decision": active_tuple[0],
                                "building_type": active_tuple[1],
                                "unit_number": active_tuple[2],
                            },
                            "current": {
                                "decision": current_tuple[0],
                                "building_type": current_tuple[1],
                                "unit_number": current_tuple[2],
                            },
                        }
                    )
        candidate_match_rate = round(candidate_matches / compared, 4) if compared else 0.0
        active_match_rate = round(active_matches / compared, 4) if compared else 0.0
        disagreement_rate = round(disagreements / compared, 4) if compared else 0.0
        shadow_advantage = round(candidate_match_rate - active_match_rate, 4)
        promote_recommended = (
            compared >= 50
            and score_delta >= 0.0
            and shadow_advantage >= 0.0
            and disagreement_rate <= 0.10
        )
        if promote_recommended:
            decision = "promote_candidate"
        else:
            decision = "keep_active"

        artifact_dir = _artifact_dir()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{model_name}_{model_version}_shadow.json"
        artifact_payload = {
            "workspace_name": workspace_name,
            "candidate_model_name": model_name,
            "candidate_model_version": model_version,
            "active_model_name": active_model.get("model_name") if active_model else None,
            "active_model_version": active_model.get("model_version") if active_model else None,
            "dataset_name": dataset_name,
            "candidate_release_benchmark": candidate_release,
            "active_release_benchmark": active_release,
            "metric_deltas": deltas,
            "score_delta": score_delta,
            "shadow_compared_rows": compared,
            "candidate_match_rate": candidate_match_rate,
            "active_match_rate": active_match_rate,
            "disagreement_rate": disagreement_rate,
            "shadow_advantage": shadow_advantage,
            "promote_recommended": promote_recommended,
            "disagreement_samples": disagreement_samples,
            "decision": decision,
            "shadow_run_id": run_id,
        }
        artifact_path.write_text(json.dumps(artifact_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        register_model_version(
            workspace_name=workspace_name,
            model_name=model_name,
            model_version=model_version,
            status="evaluated",
            evaluation_run_id=run_id,
            artifact_path=str(artifact_path),
            metrics_json={
                **(json.loads(candidate_model.get("metrics_json") or "{}") if candidate_model.get("metrics_json") else {}),
                "shadow": {
                    "dataset_name": dataset_name,
                    "candidate_model_name": model_name,
                    "candidate_model_version": model_version,
                    "active_model_name": active_model.get("model_name") if active_model else None,
                    "active_model_version": active_model.get("model_version") if active_model else None,
                    "metric_deltas": deltas,
                    "score_delta": score_delta,
                    "shadow_compared_rows": compared,
                    "candidate_match_rate": candidate_match_rate,
                    "active_match_rate": active_match_rate,
                    "disagreement_rate": disagreement_rate,
                    "shadow_advantage": shadow_advantage,
                    "promote_recommended": promote_recommended,
                    "decision": decision,
                },
            },
            notes=dumps_payload(artifact_payload),
            is_default=int(candidate_model.get("is_default") or 0),
        )

        result = {
            "run_id": run_id,
            "workspace_name": workspace_name,
            "candidate_model_name": model_name,
            "candidate_model_version": model_version,
            "active_model_name": active_model.get("model_name") if active_model else None,
            "active_model_version": active_model.get("model_version") if active_model else None,
            "dataset_name": dataset_name,
            "metric_deltas": deltas,
            "score_delta": score_delta,
            "shadow_compared_rows": compared,
            "candidate_match_rate": candidate_match_rate,
            "active_match_rate": active_match_rate,
            "disagreement_rate": disagreement_rate,
            "shadow_advantage": shadow_advantage,
            "promote_recommended": promote_recommended,
            "decision": decision,
            "artifact_path": str(artifact_path),
            "inserted": compared,
        }
        finish_run(run_id, "completed", notes=dumps_payload(result))
        return result
    except Exception as exc:
        finish_run(run_id, "failed", notes=dumps_payload({"error": str(exc)}))
        raise
