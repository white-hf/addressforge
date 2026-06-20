import json
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, "src")

from addressforge.core.common import fetch_all, db_cursor
from addressforge.pipelines.cleaning import _build_request, _upsert_stage_result, address_service

def bulk_recalibrate():
    workspace = "default"
    print(f"--- Bulk Recalibrator ---")
    print(f"Targeting all 'review' status addresses in workspace: {workspace}")
    
    # Fetch all records currently in 'review' status
    query = """
        SELECT raw.*
        FROM raw_address_record raw
        JOIN address_cleaning_result acr ON raw.raw_id = acr.raw_id
        WHERE acr.workspace_name = %s AND acr.decision = 'review'
    """
    rows = fetch_all(query, (workspace,))
    
    if not rows:
        print("No 'review' status records found to recalibrate.")
        return

    print(f"Found {len(rows)} records. Starting re-validation...")

    updated = 0
    accepted = 0
    still_review = 0
    rejected = 0 # New counter for rejected addresses
    errors = 0

    # Batch processing to show progress
    total = len(rows)
    for i, row in enumerate(rows):
        try:
            request = _build_request(row, profile="base_canada")

            # This calls the updated server logic with assist_trial and 0.22 threshold
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
            elif validation_result.get("decision") == "reject": # Increment rejected count
                rejected += 1

            if i > 0 and i % 500 == 0:
                print(f"Progress: {i}/{total} ({accepted} accepted, {rejected} rejected, {still_review} still review)")

        except Exception as e:
            errors += 1
            if errors < 5:
                print(f"Error processing row {row.get('raw_id')}: {e}")

    print(f"\n--- Recalibration Complete ---")
    print(f"Total processed: {updated}")
    print(f"Successfully Accepted: {accepted} (Auto-cleared!)")
    print(f"Automatically Rejected: {rejected}") # Print rejected count
    print(f"Still in Review: {still_review}")
    print(f"Errors: {errors}")

if __name__ == "__main__":
    bulk_recalibrate()
