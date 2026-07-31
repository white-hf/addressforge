#!/usr/bin/env python3
"""Print a read-only, structured release readiness report for one model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from addressforge.models import (
    build_release_readiness_report,
    model_release_readiness,
)


def _report_from_artifact(path: Path, base_path: Path | None = None) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    metrics = payload.get("metrics_json")
    metrics = metrics if isinstance(metrics, dict) else payload
    if base_path is not None:
        base_payload = json.loads(base_path.read_text(encoding="utf-8"))
        base_metrics = base_payload.get("metrics_json")
        base_metrics = base_metrics if isinstance(base_metrics, dict) else {}
        metrics = {
            **base_payload,
            **base_metrics,
            **metrics,
        }
    target = {
        "model_id": payload.get("model_id"),
        "workspace_name": (
            payload.get("workspace_name")
            or metrics.get("workspace_name")
            or "default"
        ),
        "model_name": payload.get("model_name") or metrics.get("model_name"),
        "model_version": (
            payload.get("model_version") or metrics.get("model_version")
        ),
        "artifact_path": str(path),
        "metrics_json": metrics,
    }
    return build_release_readiness_report(target)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate AddressForge release gates without changing registry state."
    )
    parser.add_argument("--workspace", default="default")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--model-id", type=int)
    target.add_argument("--model-version")
    target.add_argument(
        "--artifact",
        type=Path,
        help="Evaluate a local training/evaluation artifact without database access.",
    )
    parser.add_argument("--model-name", default="canada_candidate")
    parser.add_argument(
        "--base-artifact",
        type=Path,
        help="Optional earlier artifact whose immutable runtime contract is merged in memory.",
    )
    args = parser.parse_args()

    if args.artifact is not None:
        report = _report_from_artifact(args.artifact, args.base_artifact)
    else:
        report = model_release_readiness(
            workspace_name=args.workspace,
            model_id=args.model_id,
            model_name=None if args.model_id is not None else args.model_name,
            model_version=args.model_version,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report.get("ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
