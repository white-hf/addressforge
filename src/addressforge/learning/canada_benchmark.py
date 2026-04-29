from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from addressforge.core.common import canonicalize_unit_number, normalize_street_name


def _normalize_expected(value: Any, field_name: str) -> Any:
    if value in (None, ""):
        return None
    if field_name == "street_name":
        return normalize_street_name(str(value))
    if field_name == "unit_number":
        return canonicalize_unit_number(str(value))
    return str(value)


def run_canada_address_benchmark(
    benchmark_path: str | Path,
    *,
    workspace_name: str | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
    profile: str | None = None,
    parsers: tuple[str, ...] | None = None,
    decision_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from addressforge.api.server import AddressPlatformService, AddressRequest

    service = AddressPlatformService(
        default_profile=profile,
        default_parsers=parsers,
        decision_policy=decision_policy,
    )
    benchmark_file = Path(benchmark_path)
    rows = [json.loads(line) for line in benchmark_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    parse_fields = ("street_number", "street_name", "unit_number")
    validation_fields = ("building_type", "decision")

    totals = {field: 0 for field in (*parse_fields, *validation_fields)}
    matches = {field: 0 for field in (*parse_fields, *validation_fields)}
    failures: list[dict[str, Any]] = []

    for row in rows:
        expected = row.get("expected") or {}
        request = AddressRequest(
            raw_address_text=row["raw_address_text"],
            city=row.get("city"),
            province=row.get("province"),
            postal_code=row.get("postal_code"),
            profile=profile or row.get("profile") or "base_canada",
            parsers=list(parsers) if parsers else row.get("parsers"),
        )
        parsed = service.parse(request)["best_candidate"]["parsed"]
        validated = service.validate(request)

        for field in parse_fields:
            if field not in expected:
                continue
            totals[field] += 1
            predicted = parsed.get(field)
            if field == "street_name":
                predicted = normalize_street_name(predicted)
            elif field == "unit_number":
                predicted = canonicalize_unit_number(predicted)
            else:
                predicted = str(predicted) if predicted not in (None, "") else None
            gold = _normalize_expected(expected.get(field), field)
            if predicted == gold:
                matches[field] += 1
            else:
                failures.append(
                    {
                        "raw_address_text": row["raw_address_text"],
                        "field": field,
                        "expected": gold,
                        "predicted": predicted,
                    }
                )

        for field in validation_fields:
            if field not in expected:
                continue
            totals[field] += 1
            predicted = validated.get(field)
            predicted = str(predicted) if predicted not in (None, "") else None
            gold = _normalize_expected(expected.get(field), field)
            if predicted == gold:
                matches[field] += 1
            else:
                failures.append(
                    {
                        "raw_address_text": row["raw_address_text"],
                        "field": field,
                        "expected": gold,
                        "predicted": predicted,
                    }
                )

    metrics = {
        field: {
            "total": totals[field],
            "matched": matches[field],
            "accuracy": round(matches[field] / totals[field], 4) if totals[field] else 0.0,
        }
        for field in totals
    }

    return {
        "benchmark_path": str(benchmark_file),
        "case_count": len(rows),
        "evaluated_model": {
            "workspace_name": workspace_name,
            "model_name": model_name,
            "model_version": model_version,
            "profile": profile,
            "parsers": list(parsers) if parsers else None,
            "decision_policy": decision_policy or {},
        },
        "metrics": metrics,
        "failures": failures[:50],
    }
