from fastapi import APIRouter
from addressforge.services.cleaning_service import enqueue_cleaning
from pydantic import BaseModel
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME

router = APIRouter()

class CleaningRequest(BaseModel):
    workspace_name: str = None
    batch_size: int = 1000
    requested_by: str = None
    notes: str = None

@router.post("/trigger")
async def trigger(request: CleaningRequest):
    return {"status": "queued", "job": enqueue_cleaning(request.workspace_name, request.batch_size, request.requested_by, request.notes)}

@router.post("/reclean-reviews")
async def reclean_reviews(request: CleaningRequest):
    """
    Resets all 'review' status records to 'pending' to force re-evaluation with the latest ML models.
    将所有“审核 (review)”状态的记录重置为“待定 (pending)”，以强制使用最新的 ML 模型重新评估。
    """
    from addressforge.core.common import db_cursor
    workspace = request.workspace_name or ADDRESSFORGE_WORKSPACE_NAME
    
    with db_cursor() as (conn, cursor):
        cursor.execute(
            'SELECT MIN(raw_id) as min_id FROM address_cleaning_result WHERE decision = "review" AND workspace_name = %s',
            (workspace,)
        )
        first_review_row = cursor.fetchone() or {}
        min_id = first_review_row.get("min_id")

        # 1. Reset review records
        cursor.execute(
            'UPDATE address_cleaning_result SET decision = "pending", validation_json = NULL WHERE decision = "review" AND workspace_name = %s',
            (workspace,)
        )
        affected = cursor.rowcount

        # 2. Roll back only to the earliest row that was previously in review,
        # rather than any unrelated pending row in the workspace.
        if min_id:
            cursor.execute(
                'UPDATE control_setting SET setting_value = %s WHERE setting_key = "cleaning.publish.last_raw_id" AND workspace_name = %s',
                (str(min_id - 1), workspace)
            )
        conn.commit()
    
    # 3. Trigger a cleaning job immediately
    job = enqueue_cleaning(workspace, request.batch_size, request.requested_by, "Triggered via Re-clean Reviews UI")
    
    return {
        "status": "success", 
        "affected_records": affected,
        "rolled_back_to": min_id,
        "job": job
    }
