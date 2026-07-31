#!/usr/bin/env python3
"""Read-only runtime identity and fail-closed reload verification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from addressforge.api.server import AddressPlatformService


def inspect_runtime(*, workspace_name: str, check_reload: bool) -> dict[str, Any]:
    service = AddressPlatformService(workspace_name=workspace_name)
    before = service.describe_runtime()
    result: dict[str, Any] = {
        "workspace_name": workspace_name,
        "startup": before,
    }
    if not check_reload:
        return result

    model_before = service._model_service
    reranker_before = service._reranker_service
    try:
        service.reload_models()
    except Exception as exc:
        result["reload"] = {
            "status": "blocked",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "services_preserved": (
                service._model_service is model_before
                and service._reranker_service is reranker_before
            ),
            "runtime_after": service.describe_runtime(),
        }
    else:
        result["reload"] = {
            "status": "reloaded",
            "runtime_after": service.describe_runtime(),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect AddressForge runtime identity without mutating registry state."
    )
    parser.add_argument("--workspace", default="default")
    parser.add_argument(
        "--check-reload",
        action="store_true",
        help="Attempt an in-process fail-closed reload and report whether services were preserved.",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            inspect_runtime(
                workspace_name=args.workspace,
                check_reload=args.check_reload,
            ),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
