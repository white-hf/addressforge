from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from addressforge.services.review_service import batch_prescreen_review_queue, get_review_queue, submit_review
from addressforge.learning import seed_active_learning_from_errors
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME

router = APIRouter()


class ReviewSubmitRequest(BaseModel):
    task_id: int
    decision: str
    notes: str = ""
    building_type: str | None = None
    unit_number: str | None = None

@router.get("/queue")
async def review_queue(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME, limit: int = 10):
    return get_review_queue(workspace_name, limit)

@router.post("/submit")
async def submit(payload: ReviewSubmitRequest):
    return submit_review(
        task_id=payload.task_id,
        decision=payload.decision,
        notes=payload.notes,
        building_type=payload.building_type,
        unit_number=payload.unit_number,
    )

@router.post("/seed")
async def seed_active_learning(
    field: str = "decision",
    limit: int = 100
):
    try:
        result = seed_active_learning_from_errors(field=field, limit=limit)
        return {"message": "Active learning seeds queued", "inserted": result["inserted"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prescreen")
async def prescreen_review_queue(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    limit: int = 200,
    overwrite: bool = False,
):
    try:
        return batch_prescreen_review_queue(workspace_name=workspace_name, limit=limit, overwrite=overwrite)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
