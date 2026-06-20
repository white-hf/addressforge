import json
import sys
import os
import pandas as pd
from collections import defaultdict
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from addressforge.core.common import fetch_all, db_cursor

def analyze_review_backlog():
    workspace = "default"
    print(f"--- Analyzing Remaining Review Backlog for Workspace: {workspace} ---")

    # Fetch all raw_ids still in 'review' status
    raw_ids_query = """
        SELECT raw_id FROM halifax_geo_address.address_cleaning_result
        WHERE workspace_name = %s AND decision = 'review'
    """
    raw_ids_rows = fetch_all(raw_ids_query, (workspace,))
    all_raw_ids = [row['raw_id'] for row in raw_ids_rows]

    if not all_raw_ids:
        print("No addresses found in 'review' status.")
        return

    print(f"Found {len(all_raw_ids)} addresses remaining in 'review'.")

    # Fetch validation_json in batches
    batch_size = 50
    all_validation_data = []

    for i in range(0, len(all_raw_ids), batch_size):
        batch_raw_ids = all_raw_ids[i:i + batch_size]
        raw_ids_str = ", ".join(map(str, batch_raw_ids))
        
        detail_query = f"""
            SELECT raw_id, raw_address_text, validation_json
            FROM halifax_geo_address.address_cleaning_result
            WHERE raw_id IN ({raw_ids_str})
        """
        detail_rows = fetch_all(detail_query)
        all_validation_data.extend(detail_rows)
        print(f"Fetched batch {i//batch_size + 1}/{(len(all_raw_ids) + batch_size - 1) // batch_size}...")

    # Aggregation
    guard_reason_counts = defaultdict(int)
    ml_decision_counts = defaultdict(int)
    parser_disagreement_counts = defaultdict(int)
    hard_parser_disagreement_counts = defaultdict(int)
    gps_conflict_counts = defaultdict(int)
    reference_available_counts = defaultdict(int)
    
    ml_prob_bins = {"accept": defaultdict(int), "reject": defaultdict(int), "review": defaultdict(int)}

    for item in all_validation_data:
        raw_id = item['raw_id']
        validation_json = json.loads(item['validation_json'])

        shadow_assist = validation_json.get('shadow_assist', {})
        ml_decision_info = validation_json.get('ml_decision', {})
        hints = validation_json.get('hints', {})

        # Assist Guard Reason
        guard_reason = shadow_assist.get('assist_guard_reason')
        if guard_reason:
            guard_reason_counts[guard_reason] += 1
        
        # ML Decision
        ml_decision = ml_decision_info.get('ml_decision')
        if ml_decision:
            ml_decision_counts[ml_decision] += 1
        
        # Probabilities Distribution
        probabilities = ml_decision_info.get('probabilities', {})
        for label, prob in probabilities.items():
            bin_key = f"{int(prob * 10) / 10:.1f}-{int(prob * 10) / 10 + 0.1:.1f}"
            ml_prob_bins[label][bin_key] += 1

        # Parser Disagreement
        if hints.get('parser_disagreement'):
            parser_disagreement_counts['true'] += 1
        else:
            parser_disagreement_counts['false'] += 1
        
        if hints.get('hard_parser_disagreement'):
            hard_parser_disagreement_counts['true'] += 1
        else:
            hard_parser_disagreement_counts['false'] += 1

        # GPS Conflict
        if hints.get('gps_conflict'):
            gps_conflict_counts['true'] += 1
        else:
            gps_conflict_counts['false'] += 1
        
        # Reference Available
        if hints.get('reference_available'):
            reference_available_counts['true'] += 1
        else:
            reference_available_counts['false'] += 1


    print("\n--- Aggregated Analysis ---")
    print("Assist Guard Reasons:")
    for reason, count in sorted(guard_reason_counts.items()):
        print(f"  - {reason}: {count}")

    print("\nML Decision Counts:")
    for decision, count in sorted(ml_decision_counts.items()):
        print(f"  - {decision}: {count}")
    
    print("\nParser Disagreement Counts:")
    for status, count in sorted(parser_disagreement_counts.items()):
        print(f"  - Disagreement: {status}: {count}")
    
    print("\nHard Parser Disagreement Counts:")
    for status, count in sorted(hard_parser_disagreement_counts.items()):
        print(f"  - Hard Disagreement: {status}: {count}")

    print("\nGPS Conflict Counts:")
    for status, count in sorted(gps_conflict_counts.items()):
        print(f"  - GPS Conflict: {status}: {count}")
    
    print("\nReference Available Counts:")
    for status, count in sorted(reference_available_counts.items()):
        print(f"  - Reference Available: {status}: {count}")

    print("\nML Probability Distribution (Binned):")
    for label, bins in ml_prob_bins.items():
        print(f"  {label.capitalize()} Probabilities:")
        sorted_bins = sorted(bins.items())
        for bin_key, count in sorted_bins:
            print(f"    - {bin_key}: {count}")

if __name__ == "__main__":
    analyze_review_backlog()