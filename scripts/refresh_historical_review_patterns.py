import json
import sys

sys.path.insert(0, "src")

from addressforge.core.common import fetch_all
from addressforge.pipelines.cleaning import _build_request, _upsert_stage_result, address_service


def main() -> None:
    workspace = "default"
    rows = fetch_all(
        """
        SELECT raw.*
        FROM raw_address_record raw
        JOIN address_cleaning_result r ON r.raw_id = raw.raw_id AND r.workspace_name = raw.workspace_name
        WHERE raw.workspace_name=%s
          AND raw.source_name='historical_db_backfill'
          AND r.decision='review'
          AND (
            UPPER(raw.raw_address_text) REGEXP '^[[:space:]]*[0-9]{1,5}[A-Z]?[[:space:]]*-[[:space:]]*[0-9]+[A-Z]?[[:space:]]+.*[[:space:]]+[0-9]{1,5}[A-Z]?[[:space:]]+[A-Z .''-]+[[:space:]]+NS'
            OR (
              r.building_type='single_unit'
              AND UPPER(raw.raw_address_text) REGEXP '^[[:space:]]*[0-9]+[A-Z]?[[:space:]]+.*[[:space:]]+[0-9]{1,5}[A-Z]?[[:space:]]+[A-Z .''-]+[[:space:]]+NS'
            )
            OR UPPER(raw.raw_address_text) REGEXP '(^|[[:space:],-])[0-9]{1,6}[A-Z]{3,}'
            OR UPPER(raw.raw_address_text) REGEXP '[0-9](APT|APARTMENT|UNIT|SUITE|STE|ROOM|RM|FLOOR|FL)'
            OR UPPER(raw.raw_address_text) REGEXP '[A-Z]{3,}[0-9]{1,5}[A-Z]?'
          )
        ORDER BY raw.raw_id ASC
        """,
        (workspace,),
    )

    updated = 0
    accepted = 0
    still_review = 0
    multi_unit = 0

    for row in rows:
        request = _build_request(row, profile="base_canada")
        normalize_result = address_service.normalize(request)
        parse_result = address_service.parse(request)
        validation_result = address_service.validate(request)
        _upsert_stage_result(
            workspace,
            row,
            checkpoint_stage="publish",
            checkpoint_status="completed",
            normalize_result=normalize_result,
            parse_result=parse_result,
            validation_result=validation_result,
        )
        updated += 1
        if validation_result.get("decision") == "accept":
            accepted += 1
        elif validation_result.get("decision") == "review":
            still_review += 1
        if validation_result.get("building_type") == "multi_unit":
            multi_unit += 1

    print(
        json.dumps(
            {
                "targeted_rows": len(rows),
                "updated": updated,
                "accepted_after_refresh": accepted,
                "still_review_after_refresh": still_review,
                "multi_unit_after_refresh": multi_unit,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
