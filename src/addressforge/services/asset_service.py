from __future__ import annotations

import json
import hashlib
from typing import Any
from addressforge.core.common import db_cursor, fetch_all, dumps_payload
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.core.utils import logger

def promote_results_to_assets(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME) -> dict[str, Any]:
    """
    Orchestrates large-scale promotion with Reference-first merging.
    编排采用参考库优先合并策略的大规模提升任务。
    """
    logger.info("Consolidated asset promotion started (Ref-first): %s", workspace_name)
    
    # 1. Fetch high-confidence candidates including reference metadata
    # 1. 获取包含参考元数据的高置信度候选样本
    query = """
        SELECT acr.*, r.city, r.province, r.postal_code, r.country_code, 
               r.latitude, r.longitude, acr.reference_json
        FROM address_cleaning_result acr
        JOIN raw_address_record r ON acr.raw_id = r.raw_id
        WHERE acr.workspace_name = %s 
          AND acr.decision = 'accept'
          AND acr.confidence >= 0.85
          AND acr.checkpoint_status = 'completed'
    """
    results = fetch_all(query, (workspace_name,))
    
    if not results:
        return {"status": "success", "new_buildings": 0, "new_units": 0}

    buildings_added = 0
    units_added = 0

    with db_cursor() as (conn, cursor):
        for row in results:
            ref_data = json.loads(row.get("reference_json") or "{}")
            
            # --- REFERENCE-FIRST KEY LOGIC (Iteration 10) ---
            # --- 参考库优先键逻辑 (迭代 10) ---
            ext_id = ref_data.get("external_id")
            if ext_id:
                # Use a stable key derived from master reference to ensure convergence
                # 使用源自母库参考的稳定键以确保收敛
                building_key = hashlib.sha256(f"REF|{row['country_code']}|{ext_id}".encode("utf-8")).hexdigest()
            else:
                building_key = row["base_address_key"]

            # 2. Upsert Building with exact key deduplication
            # 2. 通过精确键去重进行建筑更新/插入
            cursor.execute(
                """
                INSERT INTO canonical_building (
                    workspace_name, building_key, street_number, street_name, 
                    city, province, postal_code, country_code, latitude, longitude,
                    source_attribution
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    updated_at = NOW(),
                    source_attribution = JSON_ARRAY_APPEND(COALESCE(source_attribution, '[]'), '$', %s)
                """,
                (
                    workspace_name, building_key, row["street_number"], row["street_name"],
                    row["city"], row["province"], row["postal_code"], row["country_code"],
                    row["latitude"], row["longitude"],
                    str(row["raw_id"]), str(row["raw_id"])
                )
            )
            if cursor.rowcount == 1:
                buildings_added += 1

            # 3. Upsert Unit tied to the building key
            # 3. 更新/插入绑定至建筑键的单元
            u_num = row.get("suggested_unit_number")
            if u_num:
                unit_key = hashlib.sha256(f"{building_key}|{u_num}".encode("utf-8")).hexdigest()
                cursor.execute(
                    """
                    INSERT INTO canonical_unit (
                        workspace_name, unit_key, building_key, unit_number, source_attribution
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                        updated_at = NOW(),
                        source_attribution = JSON_ARRAY_APPEND(COALESCE(source_attribution, '[]'), '$', %s)
                    """,
                    (workspace_name, unit_key, building_key, u_num, str(row["raw_id"]), str(row["raw_id"]))
                )
                if cursor.rowcount == 1:
                    units_added += 1
        
        conn.commit()

    logger.info("Asset consolidation complete. New B: %d, New U: %d", buildings_added, units_added)
    
    return {
        "status": "success",
        "new_buildings": buildings_added,
        "new_units": units_added,
        "total_processed": len(results)
    }

def get_asset_stats(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME) -> dict[str, Any]:
    """
    Retrieves statistics from the canonical tables.
    从标准资产表中检索统计数据。
    """
    b_count = fetch_all("SELECT COUNT(*) as cnt FROM canonical_building WHERE workspace_name = %s", (workspace_name,))
    u_count = fetch_all("SELECT COUNT(*) as cnt FROM canonical_unit WHERE workspace_name = %s", (workspace_name,))
    
    return {
        "total_buildings": b_count[0]["cnt"] if b_count else 0,
        "total_units": u_count[0]["cnt"] if u_count else 0,
        "workspace": workspace_name
    }
