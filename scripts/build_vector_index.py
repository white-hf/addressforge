import sys
import os
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from addressforge.core.common import fetch_all
from addressforge.core.retrieval import get_vector_engine

def build_index(workspace_name: str = "default"):
    print(f"--- Phase 12: Building Vector Index for Workspace '{workspace_name}' ---")
    
    # Fetch active references from the database
    query = """
        SELECT
            reference_id,
            source_name,
            external_id,
            street_number,
            street_name,
            unit_number,
            city,
            municipality,
            county,
            province,
            postal_code,
            reference_lat,
            reference_lon,
            quality_score
        FROM external_building_reference
        WHERE is_active = 1 AND workspace_name = %s
    """
    records = fetch_all(query, (workspace_name,))
    
    if not records:
        print("No active references found. Are you sure the database is populated?")
        # Fallback to without workspace_name if empty
        query_fallback = """
        SELECT
            reference_id,
            source_name,
            external_id,
            street_number,
            street_name,
            unit_number,
            city,
            municipality,
            county,
            province,
            postal_code,
            reference_lat,
            reference_lon,
            quality_score
        FROM external_building_reference
        WHERE is_active = 1
        """
        records = fetch_all(query_fallback)
        if not records:
             print("Still no references found. Exiting.")
             return
        print(f"Fallback: Fetched {len(records)} active references globally.")
    else:
        print(f"Fetched {len(records)} active references.")
        
    engine = get_vector_engine()
    engine.build_index(records)
    print("Vector Index build complete.")

if __name__ == "__main__":
    build_index()
