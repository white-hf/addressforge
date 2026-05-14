from fastapi import APIRouter, HTTPException
from addressforge.services.model_service import register_model, promote, deprecate, fetch_models
from addressforge.models.registry import rollback_model
from pydantic import BaseModel

router = APIRouter()

class ModelRequest(BaseModel):
    workspace_name: str = None
    model_name: str
    model_version: str
    model_family: str = "baseline"
    notes: str = None

@router.post("/register")
async def register(request: ModelRequest):
    return {"status": "ok", "model": register_model(request.workspace_name, request.model_name, request.model_version, model_family=request.model_family, notes=request.notes)}

@router.post("/promote")
async def promote_m(request: dict):
    return {"status": "ok", "model": promote(request.get("workspace_name"), request.get("model_id"), request.get("notes"))}

@router.post("/rollback")
async def rollback_m(request: dict):
    """
    Rolls back the active model to the previously promoted version.
    将活动模型回滚到上一个提升的版本。
    """
    try:
        model = rollback_model(request.get("workspace_name", "default"), request.get("notes"))
        return {"status": "ok", "model": model}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
