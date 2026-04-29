from fastapi import APIRouter
from addressforge.services.cleaning_service import enqueue_cleaning
from pydantic import BaseModel

router = APIRouter()

class CleaningRequest(BaseModel):
    workspace_name: str = None
    batch_size: int = 1000
    requested_by: str = None
    notes: str = None

@router.post("/trigger")
async def trigger(request: CleaningRequest):
    return {"status": "queued", "job": enqueue_cleaning(request.workspace_name, request.batch_size, request.requested_by, request.notes)}
