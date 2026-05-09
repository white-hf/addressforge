import sys
import os
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from addressforge.core.common import fetch_all, db_cursor

def seed_negative_gold():
    # 1. Identify garbage or extremely low-confidence samples
    bad_samples = [
        {"raw_id": 20579, "reason": "non_existent"},  # Charlene Other NS
        {"raw_id": 26985, "reason": "invalid_format"}, # house Halifax NS
        {"raw_id": 60749, "reason": "invalid_format"}, # ******
    ]
    
    workspace = "default"
    
    with db_cursor() as (conn, cursor):
        for s in bad_samples:
            # Upsert into gold_label as 'rejected'
            # Using alias for MySQL 8 compatibility
            query = """
                INSERT INTO gold_label (workspace_name, source_name, source_id, task_type, label_json, review_status, label_source, notes)
                VALUES (%s, 'system_seed', %s, 'decision', %s, 'rejected', 'human', %s) AS new_data
                ON DUPLICATE KEY UPDATE review_status = 'rejected', notes = new_data.notes
            """
            label_json = '{"decision": "reject"}'
            notes = f"[REJECT:{s['reason']}] Seeded by system for ML training."
            cursor.execute(query, (workspace, str(s["raw_id"]), label_json, notes))
        conn.commit()
    
    print(f"Successfully seeded {len(bad_samples)} negative gold labels.")

if __name__ == "__main__":
    seed_negative_gold()
