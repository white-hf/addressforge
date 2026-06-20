from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List
from addressforge.core.common import fetch_all, db_cursor, normalize_street_name, normalize_city, normalize_province
from addressforge.core.profiles.factory import get_profile
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.services.asset_service import _canonical_building_key, _normalize_canonical_unit_value

logger = logging.getLogger("addressforge")

def run_reference_fusion(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME) -> Dict[str, Any]:
    """
    Groups and merges duplicate references from external_building_reference
    and populates canonical_building.
    """
    logger.info("Starting Reference Fusion (Entity Fusion) for workspace %s", workspace_name)
    
    # 1. Fetch all active references
    query = """
        SELECT reference_id, source_name, external_id, street_number, street_name, 
               unit_number, city, municipality, province, postal_code, 
               reference_lat, reference_lon, reference_tier, quality_score, raw_payload
        FROM external_building_reference
        WHERE is_active = 1 AND workspace_name = %s
    """
    records = fetch_all(query, (workspace_name,))
    if not records:
        logger.info("No active references found for fusion in workspace %s", workspace_name)
        return {"buildings_fused": 0, "total_references_processed": 0}
        
    profile_obj = get_profile("CA")
    
    # Group references by normalized base address to find duplicates
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for r in records:
        sn = str(r["street_number"] or "").strip().upper()
        st = (normalize_street_name(r["street_name"]) or "").upper()
        city = (normalize_city(r["city"] or r["municipality"]) or "").upper()
        prov = (normalize_province(r["province"], profile_obj) or "").upper()
        
        if not sn or not st:
            continue
            
        key = (sn, st, city, prov)
        groups.setdefault(key, []).append(r)
        
    buildings_fused = 0
    total_references_processed = len(records)
    
    with db_cursor() as (conn, cursor):
        for key, ref_list in groups.items():
            # Sort references to find the best representative:
            # 1. Authoritative tier first
            # 2. geonova source first
            # 3. Highest quality score
            def sort_key(ref):
                tier_val = {"authoritative": 3, "semi_authoritative": 2, "weak": 1}.get(ref["reference_tier"], 0)
                source_val = 1 if ref["source_name"] == "geonova" else 0
                qs_val = float(ref["quality_score"] or 0.0)
                return (-tier_val, -source_val, -qs_val)
                
            ref_list.sort(key=sort_key)
            best_ref = ref_list[0]
            
            # Generate building key based on best_ref's external_id
            ext_id = str(best_ref["external_id"] or "").strip()
            building_key = hashlib.sha256(f"REF|CA|{ext_id}".encode("utf-8")).hexdigest()
            
            # Aggregate source attribution from all duplicates in the group
            source_attribution = []
            for ref in ref_list:
                source_attribution.append({
                    "source_name": ref["source_name"],
                    "external_id": ref["external_id"],
                    "reference_id": ref["reference_id"]
                })
                
            # Upsert into canonical_building
            cursor.execute(
                """
                INSERT INTO canonical_building (
                    workspace_name, building_key, street_number, street_name,
                    city, province, postal_code, country_code, latitude, longitude,
                    source_attribution, is_active
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1) AS new_row
                ON DUPLICATE KEY UPDATE
                    street_number = new_row.street_number,
                    street_name = new_row.street_name,
                    city = new_row.city,
                    province = new_row.province,
                    postal_code = new_row.postal_code,
                    latitude = COALESCE(new_row.latitude, canonical_building.latitude),
                    longitude = COALESCE(new_row.longitude, canonical_building.longitude),
                    source_attribution = new_row.source_attribution,
                    is_active = 1,
                    updated_at = NOW()
                """,
                (
                    workspace_name,
                    building_key,
                    best_ref["street_number"],
                    best_ref["street_name"],
                    best_ref["city"] or best_ref["municipality"],
                    best_ref["province"],
                    best_ref["postal_code"],
                    "CA",
                    float(best_ref["reference_lat"]) if best_ref["reference_lat"] is not None else None,
                    float(best_ref["reference_lon"]) if best_ref["reference_lon"] is not None else None,
                    json.dumps(source_attribution)
                )
            )
            buildings_fused += 1
            
        conn.commit()
        
    logger.info("Reference Fusion completed. Fused %d buildings from %d references.", buildings_fused, total_references_processed)
    return {"buildings_fused": buildings_fused, "total_references_processed": total_references_processed}


def run_unit_mining(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME) -> Dict[str, Any]:
    """
    Extracts units from successful delivery / highly confident cleaning results,
    populates canonical_unit, reducing enrich routing gaps.
    """
    logger.info("Starting Unit Mining for workspace %s", workspace_name)
    
    # Fetch high-confidence accepted cleaning results with a unit number
    query = """
        SELECT result_id, raw_id, raw_address_text, suggested_unit_number, base_address_key, reference_json
        FROM address_cleaning_result
        WHERE workspace_name = %s
          AND decision = 'accept'
          AND confidence >= 0.90
          AND suggested_unit_number IS NOT NULL
          AND suggested_unit_number != ''
    """
    results = fetch_all(query, (workspace_name,))
    if not results:
        logger.info("No candidate records found for unit mining in workspace %s", workspace_name)
        return {"units_mined": 0}
        
    units_mined = 0
    with db_cursor() as (conn, cursor):
        for row in results:
            u_num = _normalize_canonical_unit_value(row["suggested_unit_number"])
            if not u_num:
                continue
                
            # Derive building_key:
            # Check if reference_json has external_id, else use base_address_key
            ext_id = None
            if row.get("reference_json"):
                try:
                    ref_data = json.loads(row["reference_json"]) if isinstance(row["reference_json"], str) else row["reference_json"]
                    ext_id = str(ref_data.get("external_id") or "").strip()
                except Exception:
                    pass
            
            if ext_id:
                building_key = hashlib.sha256(f"REF|CA|{ext_id}".encode("utf-8")).hexdigest()
            else:
                building_key = str(row.get("base_address_key") or "").strip()
                
            if not building_key:
                continue
                
            # Verify building exists in canonical_building first (foreign key constraint)
            cursor.execute(
                "SELECT 1 FROM canonical_building WHERE workspace_name = %s AND building_key = %s",
                (workspace_name, building_key)
            )
            if not cursor.fetchone():
                # If building doesn't exist, skip to ensure integrity
                continue
                
            unit_key = hashlib.sha256(f"{building_key}|{u_num}".encode("utf-8")).hexdigest()
            
            # Upsert into canonical_unit
            source_attribution = [{
                "mined_from_result_id": row["result_id"],
                "raw_id": row["raw_id"]
            }]
            
            cursor.execute(
                """
                INSERT INTO canonical_unit (
                    workspace_name, unit_key, building_key, unit_number, unit_type, source_attribution, is_active
                ) VALUES (%s, %s, %s, %s, 'apartment', %s, 1)
                ON DUPLICATE KEY UPDATE
                    is_active = 1,
                    source_attribution = JSON_ARRAY_APPEND(COALESCE(source_attribution, '[]'), '$', JSON_EXTRACT(%s, '$[0]')),
                    updated_at = NOW()
                """,
                (
                    workspace_name,
                    unit_key,
                    building_key,
                    u_num,
                    json.dumps(source_attribution),
                    json.dumps(source_attribution)
                )
            )
            if cursor.rowcount == 1:
                units_mined += 1
                
        conn.commit()
        
    logger.info("Unit Mining completed. Mined %d new units.", units_mined)
    return {"units_mined": units_mined}


def run_reference_enrichment_pipeline(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME) -> Dict[str, Any]:
    """
    Executes both reference fusion and unit mining as a combined enrichment pipeline.
    """
    fusion_res = run_reference_fusion(workspace_name)
    mining_res = run_unit_mining(workspace_name)
    return {
        "status": "success",
        "buildings_fused": fusion_res["buildings_fused"],
        "total_references_processed": fusion_res["total_references_processed"],
        "units_mined": mining_res["units_mined"]
    }
