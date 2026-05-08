from fastapi import APIRouter, HTTPException
from addressforge.services.job_service import enqueue_job, fetch_job_status, fetch_jobs
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from pydantic import BaseModel

router = APIRouter()

class JobTriggerRequest(BaseModel):
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME
    requested_by: str = None
    priority: int = 0
    notes: str = None

class GenericJobRequest(BaseModel):
    job_action: str
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME
    payload: dict = {}
    requested_by: str = None
    priority: int = 0

from addressforge.learning.gold import seed_active_learning_queue, freeze_gold_set

from addressforge.pipelines.training_pipeline import run_training_pipeline

from addressforge.services.asset_service import promote_results_to_assets

@router.post("/trigger")
async def trigger_generic_job(request: GenericJobRequest):
    """
    Standard entry point for UI-triggered jobs.
    UI 触发任务的标准入口。
    """
    # 1. Direct Execution Pathways (Synchronous or Pipeline Orchestrated)
    # 1. 直接执行路径 (同步或流水线编排)
    if request.job_action == "seed_review_batch":
        limit = request.payload.get("limit", 50)
        result = seed_active_learning_queue(
            workspace_name=request.workspace_name,
            limit=limit
        )
        return {
            "status": "completed", 
            "job": {"job_id": result.get("run_id")}, 
            "inserted": result.get("inserted"),
            "breakdown": result.get("breakdown")
        }

    # 2. Pipeline Execution Pathway (Async Worker Background)
    # 2. 流水线执行路径 (异步 Worker 后台)
    kind_map = {
        "ingestion_once": "ingestion_once",
        "cleaning_once": "cleaning_once",
        "training_once": "training_once",
        "evaluation_once": "evaluation_once",
        "freeze_human_gold": "gold_freeze_once",
        "promote_assets": "promote_assets_once"
    }
    
    job_kind = kind_map.get(request.job_action, request.job_action)
    
    job = enqueue_job(
        request.workspace_name, 
        job_kind, 
        request.payload, 
        request.requested_by or "ui", 
        request.priority
    )
    return {"status": "queued", "job": job}


@router.post("/train")
async def trigger_training(request: JobTriggerRequest, model_name: str = "default_model", model_version: str = "v1"):
    job = enqueue_job(request.workspace_name, "ml_train", {"model_name": model_name, "model_version": model_version, "notes": request.notes}, request.requested_by, request.priority)
    return {"status": "queued", "job": job}

@router.get("/{job_id}/status")
async def get_job(job_id: int):
    job = fetch_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.post("/reference-import")
async def trigger_ref_import(request: JobTriggerRequest, csv_path: str = None, batch_size: int = 5000):
    job = enqueue_job(request.workspace_name, "reference_import_once", {"csv_path": csv_path, "batch_size": batch_size, "notes": request.notes}, request.requested_by, request.priority)
    return {"status": "queued", "job": job}

@router.post("/export")
async def trigger_export(request: JobTriggerRequest, export_root: str = None):
    job = enqueue_job(request.workspace_name, "workspace_export_once", {"export_root": export_root, "notes": request.notes}, request.requested_by, request.priority)
    return {"status": "queued", "job": job}
