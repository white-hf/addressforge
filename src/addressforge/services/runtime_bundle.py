from __future__ import annotations

from typing import Any, Literal, Mapping

from addressforge.models.runtime_manifest import (
    resolve_runtime_manifest,
    summarize_validation_failure,
    validate_runtime_manifest,
)
from addressforge.services.model_service import build_model_service_from_manifest
from addressforge.services.reranker_service import build_reranker_service_from_manifest

RuntimeBundleMode = Literal["governed", "compatibility"]


def _runtime_load_issues(model_service: Any, reranker_service: Any) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if getattr(model_service, "model", None) is None:
        issues.append(
            {
                "code": "decision_model_load_failed",
                "message": "Decision model could not be loaded from the governed manifest",
            }
        )
    if bool(getattr(model_service, "_legacy_mode", False)):
        issues.append(
            {
                "code": "decision_model_legacy_fallback",
                "message": "Decision model entered legacy compatibility mode",
            }
        )
    if getattr(model_service, "_artifact_source", None) != "manifest":
        issues.append(
            {
                "code": "decision_model_source_mismatch",
                "message": (
                    "Decision model artifact source is "
                    f"{getattr(model_service, '_artifact_source', None) or 'unknown'}, expected manifest"
                ),
            }
        )
    if getattr(model_service, "bt_model", None) is None:
        issues.append(
            {
                "code": "building_type_model_load_failed",
                "message": "BuildingType model could not be loaded from the governed manifest",
            }
        )
    if getattr(reranker_service, "model", None) is None:
        issues.append(
            {
                "code": "reranker_model_load_failed",
                "message": "Reranker model could not be loaded from the governed manifest",
            }
        )
    if getattr(reranker_service, "_artifact_source", None) != "manifest":
        issues.append(
            {
                "code": "reranker_model_source_mismatch",
                "message": (
                    "Reranker artifact source is "
                    f"{getattr(reranker_service, '_artifact_source', None) or 'unknown'}, expected manifest"
                ),
            }
        )
    return issues


def build_runtime_bundle_from_model_row(
    model_row: Mapping[str, Any],
    *,
    mode: RuntimeBundleMode = "governed",
) -> dict[str, Any]:
    """
    Build one isolated runtime bundle from one registry row.

    ``governed`` mode validates the immutable contract before loading and rejects
    every fallback. ``compatibility`` mode preserves legacy loading behavior but
    returns the failed contract evidence and explicit runtime identity.
    """
    if mode not in {"governed", "compatibility"}:
        raise ValueError(f"Unsupported runtime bundle mode: {mode}")

    manifest = resolve_runtime_manifest(model_row)
    validation = validate_runtime_manifest(
        manifest,
        model_row=model_row,
        require_hashes=mode == "governed",
        check_files=True,
    )
    base_identity = {
        "mode": mode,
        "registry": dict(manifest.get("_registry_identity") or {}),
        "contract": validation.to_dict(),
    }
    if mode == "governed" and not validation.ok:
        return {
            "ok": False,
            "reason": "runtime_manifest_invalid",
            "detail": summarize_validation_failure(validation),
            "manifest": manifest,
            "runtime_identity": base_identity,
        }

    binding = manifest.get("runtime_binding")
    binding = binding if isinstance(binding, dict) else {}
    profile = (
        binding.get("profile")
        or manifest.get("profile")
        or model_row.get("default_profile")
        or "base_canada"
    )
    parsers = tuple(
        binding.get("parsers")
        or manifest.get("parsers")
        or ("simple_rule", "hybrid_canada", "libpostal")
    )
    decision_policy = (
        binding.get("decision_policy")
        if isinstance(binding.get("decision_policy"), dict)
        else manifest.get("decision_policy")
        if isinstance(manifest.get("decision_policy"), dict)
        else {}
    )

    model_service = build_model_service_from_manifest(manifest)
    reranker_service = build_reranker_service_from_manifest(manifest)
    runtime_load_issues = _runtime_load_issues(model_service, reranker_service)
    runtime_identity = {
        **base_identity,
        "profile": profile,
        "parsers": list(parsers),
        "decision_model": model_service.describe_runtime(),
        "building_type_model": {
            "model_path": str(getattr(model_service, "bt_model_path", "")),
            "artifact_source": (
                "manifest"
                if isinstance(manifest.get("building_type_model_artifact"), dict)
                and manifest.get("building_type_model_artifact")
                else "fallback"
            ),
            "loaded": getattr(model_service, "bt_model", None) is not None,
        },
        "reranker_model": reranker_service.describe_runtime(),
        "runtime_load_issues": runtime_load_issues,
    }
    if mode == "governed" and runtime_load_issues:
        return {
            "ok": False,
            "reason": "runtime_artifact_load_failed",
            "detail": "; ".join(issue["message"] for issue in runtime_load_issues),
            "manifest": manifest,
            "runtime_identity": runtime_identity,
        }

    return {
        "ok": True,
        "mode": mode,
        "profile": str(profile),
        "parsers": parsers,
        "decision_policy": decision_policy,
        "model_service": model_service,
        "reranker_service": reranker_service,
        "manifest": manifest,
        "runtime_identity": runtime_identity,
    }
