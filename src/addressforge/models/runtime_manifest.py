from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

RUNTIME_MANIFEST_SCHEMA_VERSION = "1.0"
RUNTIME_ARTIFACT_HASH_ALGORITHM = "sha256"

REQUIRED_ARTIFACT_PATHS: dict[str, tuple[str, ...]] = {
    "decision_model_artifact": ("model_path", "metadata_path"),
    "reranker_model_artifact": ("model_path",),
    "building_type_model_artifact": ("model_path",),
}


@dataclass(frozen=True)
class RuntimeManifestIssue:
    code: str
    message: str
    field: str | None = None
    component: str | None = None


@dataclass(frozen=True)
class RuntimeManifestValidation:
    ok: bool
    issues: tuple[RuntimeManifestIssue, ...]
    identity: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": [asdict(issue) for issue in self.issues],
            "identity": self.identity,
        }


def json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if value in (None, ""):
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bind_artifact_hashes(
    descriptor: Mapping[str, Any],
    *,
    path_fields: Iterable[str],
) -> dict[str, Any]:
    """Return an artifact descriptor bound to the current physical file hashes."""
    result = dict(descriptor)
    hashes = json_object(result.get("sha256"))
    for field in path_fields:
        raw_path = result.get(field)
        if not raw_path:
            raise ValueError(f"Required artifact path is missing: {field}")
        path = Path(str(raw_path))
        if not path.exists():
            raise FileNotFoundError(f"Required artifact file is missing: {path}")
        hashes[field] = sha256_file(path)
    result["sha256"] = hashes
    return result


def runtime_bundle_id(
    workspace_name: str,
    model_name: str,
    model_version: str,
) -> str:
    return f"{workspace_name}:{model_name}:{model_version}"


def apply_runtime_manifest_contract(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """
    Add the immutable runtime contract fields and bind required artifact hashes.

    This function is intended for newly produced training manifests. Existing
    legacy manifests should be audited with ``validate_runtime_manifest`` rather
    than silently upgraded.
    """
    result = dict(manifest)
    workspace_name = str(result.get("workspace_name") or "").strip()
    model_name = str(result.get("model_name") or "").strip()
    model_version = str(result.get("model_version") or "").strip()
    if not all((workspace_name, model_name, model_version)):
        raise ValueError("workspace_name, model_name, and model_version are required")

    result["manifest_schema_version"] = RUNTIME_MANIFEST_SCHEMA_VERSION
    result["runtime_bundle_id"] = runtime_bundle_id(workspace_name, model_name, model_version)
    result["artifact_hash_algorithm"] = RUNTIME_ARTIFACT_HASH_ALGORITHM

    for component, path_fields in REQUIRED_ARTIFACT_PATHS.items():
        descriptor = result.get(component)
        if not isinstance(descriptor, dict) or not descriptor:
            continue
        result[component] = bind_artifact_hashes(descriptor, path_fields=path_fields)
    return result


def resolve_runtime_manifest(model_row: Mapping[str, Any]) -> dict[str, Any]:
    """
    Resolve one registry row into a single manifest view.

    Registry metrics have the highest precedence, followed by the nested metrics
    in an evaluation artifact, then the artifact root. Resolution errors remain
    explicit so callers can fail closed.
    """
    artifact_payload: dict[str, Any] = {}
    resolution_issues: list[dict[str, str]] = []
    artifact_path = model_row.get("artifact_path")
    if artifact_path:
        path = Path(str(artifact_path))
        if not path.exists():
            resolution_issues.append(
                {
                    "code": "manifest_file_missing",
                    "message": f"Registry artifact_path does not exist: {path}",
                }
            )
        elif not path.is_file():
            resolution_issues.append(
                {
                    "code": "manifest_path_not_file",
                    "message": f"Registry artifact_path is not a file: {path}",
                }
            )
        else:
            try:
                artifact_payload = json_object(path.read_text(encoding="utf-8"))
                if not artifact_payload:
                    resolution_issues.append(
                        {
                            "code": "manifest_file_invalid",
                            "message": f"Registry artifact_path is not a JSON object: {path}",
                        }
                    )
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                resolution_issues.append(
                    {
                        "code": "manifest_file_unreadable",
                        "message": f"Failed to read registry artifact_path {path}: {exc}",
                    }
                )

    nested_metrics = json_object(artifact_payload.get("metrics_json"))
    registry_metrics = json_object(model_row.get("metrics_json"))
    resolved = {
        **artifact_payload,
        **nested_metrics,
        **registry_metrics,
    }
    resolved.setdefault("workspace_name", model_row.get("workspace_name"))
    resolved.setdefault("model_name", model_row.get("model_name"))
    resolved.setdefault("model_version", model_row.get("model_version"))
    resolved["_registry_identity"] = {
        "model_id": model_row.get("model_id"),
        "workspace_name": model_row.get("workspace_name"),
        "model_name": model_row.get("model_name"),
        "model_version": model_row.get("model_version"),
        "artifact_path": artifact_path,
    }
    resolved["_resolution_issues"] = resolution_issues
    return resolved


def validate_runtime_manifest(
    manifest: Mapping[str, Any],
    *,
    model_row: Mapping[str, Any] | None = None,
    require_hashes: bool = True,
    check_files: bool = True,
) -> RuntimeManifestValidation:
    issues: list[RuntimeManifestIssue] = []
    registry_identity = dict(model_row or manifest.get("_registry_identity") or {})

    for issue in manifest.get("_resolution_issues") or []:
        if isinstance(issue, dict):
            issues.append(
                RuntimeManifestIssue(
                    code=str(issue.get("code") or "manifest_resolution_error"),
                    message=str(issue.get("message") or "Manifest resolution failed"),
                )
            )

    schema_version = str(manifest.get("manifest_schema_version") or "").strip()
    if schema_version != RUNTIME_MANIFEST_SCHEMA_VERSION:
        issues.append(
            RuntimeManifestIssue(
                code="manifest_schema_version_invalid",
                message=(
                    f"manifest_schema_version must be {RUNTIME_MANIFEST_SCHEMA_VERSION}; "
                    f"got {schema_version or 'missing'}"
                ),
                field="manifest_schema_version",
            )
        )

    identity = {
        "model_id": registry_identity.get("model_id"),
        "workspace_name": manifest.get("workspace_name"),
        "model_name": manifest.get("model_name"),
        "model_version": manifest.get("model_version"),
        "runtime_bundle_id": manifest.get("runtime_bundle_id"),
        "manifest_schema_version": manifest.get("manifest_schema_version"),
        "artifact_hash_algorithm": manifest.get("artifact_hash_algorithm"),
        "artifact_path": registry_identity.get("artifact_path"),
    }

    for field in ("workspace_name", "model_name", "model_version"):
        manifest_value = str(manifest.get(field) or "").strip()
        registry_value = str(registry_identity.get(field) or "").strip()
        if not manifest_value:
            issues.append(
                RuntimeManifestIssue(
                    code="manifest_identity_missing",
                    message=f"Manifest identity field is missing: {field}",
                    field=field,
                )
            )
        elif registry_value and manifest_value != registry_value:
            issues.append(
                RuntimeManifestIssue(
                    code="manifest_identity_mismatch",
                    message=f"{field} differs: manifest={manifest_value}, registry={registry_value}",
                    field=field,
                )
            )

    expected_bundle_id = runtime_bundle_id(
        str(manifest.get("workspace_name") or ""),
        str(manifest.get("model_name") or ""),
        str(manifest.get("model_version") or ""),
    )
    if manifest.get("runtime_bundle_id") != expected_bundle_id:
        issues.append(
            RuntimeManifestIssue(
                code="runtime_bundle_id_invalid",
                message=(
                    f"runtime_bundle_id must be {expected_bundle_id}; "
                    f"got {manifest.get('runtime_bundle_id') or 'missing'}"
                ),
                field="runtime_bundle_id",
            )
        )

    if manifest.get("artifact_hash_algorithm") != RUNTIME_ARTIFACT_HASH_ALGORITHM:
        issues.append(
            RuntimeManifestIssue(
                code="artifact_hash_algorithm_invalid",
                message=f"artifact_hash_algorithm must be {RUNTIME_ARTIFACT_HASH_ALGORITHM}",
                field="artifact_hash_algorithm",
            )
        )

    runtime_binding = manifest.get("runtime_binding")
    if not isinstance(runtime_binding, dict):
        issues.append(
            RuntimeManifestIssue(
                code="runtime_binding_missing",
                message="runtime_binding must be present and must be an object",
                field="runtime_binding",
            )
        )
    else:
        if not str(runtime_binding.get("profile") or "").strip():
            issues.append(
                RuntimeManifestIssue(
                    code="runtime_profile_missing",
                    message="runtime_binding.profile is required",
                    field="runtime_binding.profile",
                )
            )
        parsers = runtime_binding.get("parsers")
        if not isinstance(parsers, list) or not parsers:
            issues.append(
                RuntimeManifestIssue(
                    code="runtime_parsers_missing",
                    message="runtime_binding.parsers must be a non-empty list",
                    field="runtime_binding.parsers",
                )
            )
        if not isinstance(runtime_binding.get("decision_policy"), dict):
            issues.append(
                RuntimeManifestIssue(
                    code="runtime_policy_missing",
                    message="runtime_binding.decision_policy must be an object",
                    field="runtime_binding.decision_policy",
                )
            )

    component_identity: dict[str, Any] = {}
    for component, required_paths in REQUIRED_ARTIFACT_PATHS.items():
        descriptor = manifest.get(component)
        if not isinstance(descriptor, dict) or not descriptor:
            issues.append(
                RuntimeManifestIssue(
                    code="artifact_component_missing",
                    message=f"Required runtime artifact component is missing: {component}",
                    component=component,
                )
            )
            component_identity[component] = None
            continue

        hashes = json_object(descriptor.get("sha256"))
        component_identity[component] = {
            "model_type": descriptor.get("model_type"),
            "paths": {field: descriptor.get(field) for field in required_paths},
            "sha256": {field: hashes.get(field) for field in required_paths},
        }
        for field in required_paths:
            raw_path = descriptor.get(field)
            qualified_field = f"{component}.{field}"
            if not raw_path:
                issues.append(
                    RuntimeManifestIssue(
                        code="artifact_path_missing",
                        message=f"Required artifact path is missing: {qualified_field}",
                        field=qualified_field,
                        component=component,
                    )
                )
                continue

            path = Path(str(raw_path))
            if check_files and not path.exists():
                issues.append(
                    RuntimeManifestIssue(
                        code="artifact_file_missing",
                        message=f"Required artifact file does not exist: {path}",
                        field=qualified_field,
                        component=component,
                    )
                )
                continue

            expected_hash = str(hashes.get(field) or "").strip().lower()
            if require_hashes and not expected_hash:
                issues.append(
                    RuntimeManifestIssue(
                        code="artifact_hash_missing",
                        message=f"Required SHA256 is missing: {qualified_field}",
                        field=qualified_field,
                        component=component,
                    )
                )
                continue

            if check_files and expected_hash:
                try:
                    actual_hash = sha256_file(path)
                except OSError as exc:
                    issues.append(
                        RuntimeManifestIssue(
                            code="artifact_file_unreadable",
                            message=f"Failed to hash artifact {path}: {exc}",
                            field=qualified_field,
                            component=component,
                        )
                    )
                    continue
                if actual_hash != expected_hash:
                    issues.append(
                        RuntimeManifestIssue(
                            code="artifact_hash_mismatch",
                            message=(
                                f"SHA256 mismatch for {path}: "
                                f"expected={expected_hash}, actual={actual_hash}"
                            ),
                            field=qualified_field,
                            component=component,
                        )
                    )

    identity["components"] = component_identity
    return RuntimeManifestValidation(ok=not issues, issues=tuple(issues), identity=identity)


def summarize_validation_failure(validation: RuntimeManifestValidation, *, limit: int = 5) -> str:
    messages = [issue.message for issue in validation.issues[:limit]]
    remaining = len(validation.issues) - len(messages)
    if remaining > 0:
        messages.append(f"... and {remaining} more issue(s)")
    return "; ".join(messages)
