from fastapi import APIRouter, HTTPException
from addressforge.services.model_service import register_model, promote, deprecate, fetch_models
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
