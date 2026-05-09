from pydantic import BaseModel
from fastapi import APIRouter, BackgroundTasks, HTTPException
from addressforge.services.review_service import batch_prescreen_review_queue, get_review_queue, submit_review
from addressforge.learning import (
    seed_active_learning_from_errors,
    seed_apartment_unit_hard_samples,
    seed_decision_calibration_review_queue,
    seed_decision_minority_label_review_queue,
    seed_label_consistency_relabel_queue,
    seed_semantic_disambiguation_review_queue,
)
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME

router = APIRouter()


def _schedule_review_prescreen(background_tasks: BackgroundTasks, workspace_name: str, limit: int) -> None:
    if limit <= 0:
        return
    background_tasks.add_task(
        batch_prescreen_review_queue,
        workspace_name=workspace_name,
        limit=limit,
        overwrite=False,
    )


class ReviewSubmitRequest(BaseModel):
    task_id: int
    decision: str
    notes: str = ""
    building_type: str | None = None
    unit_number: str | None = None
    street_number: str | None = None
    street_name: str | None = None
    city: str | None = None
    province: str | None = None
    postal_code: str | None = None

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
        street_number=payload.street_number,
        street_name=payload.street_name,
        city=payload.city,
        province=payload.province,
        postal_code=payload.postal_code,
    )

@router.post("/seed")
async def seed_active_learning(
    background_tasks: BackgroundTasks,
    field: str = "decision",
    limit: int = 100,
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
):
    try:
        result = seed_active_learning_from_errors(workspace_name=workspace_name, field=field, limit=limit)
        _schedule_review_prescreen(background_tasks, workspace_name, int(result.get("inserted") or 0))
        return {
            "message": "Active learning seeds queued",
            "prescreen_status": "scheduled",
            **result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/seed-apartment-units")
async def seed_apartment_unit_queue(
    background_tasks: BackgroundTasks,
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    limit: int = 150,
    confidence_threshold: float = 0.84,
):
    try:
        result = seed_apartment_unit_hard_samples(
            workspace_name=workspace_name,
            limit=limit,
            confidence_threshold=confidence_threshold,
        )
        _schedule_review_prescreen(background_tasks, workspace_name, int(result.get("inserted") or 0))
        return {
            "message": "Apartment/unit hard-sample seeds queued",
            "prescreen_status": "scheduled",
            **result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/seed-relabel-consistency")
async def seed_relabel_consistency_queue(
    background_tasks: BackgroundTasks,
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    limit: int = 100,
):
    try:
        result = seed_label_consistency_relabel_queue(
            workspace_name=workspace_name,
            limit=limit,
        )
        _schedule_review_prescreen(background_tasks, workspace_name, int(result.get("inserted") or 0))
        return {
            "message": "Relabel consistency review seeds queued",
            "prescreen_status": "scheduled",
            **result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/seed-semantic-disambiguation")
async def seed_semantic_disambiguation_queue(
    background_tasks: BackgroundTasks,
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    limit: int = 100,
    confidence_threshold: float = 0.88,
):
    try:
        result = seed_semantic_disambiguation_review_queue(
            workspace_name=workspace_name,
            limit=limit,
            confidence_threshold=confidence_threshold,
        )
        _schedule_review_prescreen(background_tasks, workspace_name, int(result.get("inserted") or 0))
        return {
            "message": "Semantic disambiguation review seeds queued",
            "prescreen_status": "scheduled",
            **result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/seed-decision-calibration")
async def seed_decision_calibration_queue(
    background_tasks: BackgroundTasks,
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    limit: int = 80,
    confidence_threshold: float = 0.66,
):
    try:
        result = seed_decision_calibration_review_queue(
            workspace_name=workspace_name,
            limit=limit,
            confidence_threshold=confidence_threshold,
        )
        _schedule_review_prescreen(background_tasks, workspace_name, int(result.get("inserted") or 0))
        return {
            "message": "Decision calibration review seeds queued",
            "prescreen_status": "scheduled",
            **result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/seed-decision-minority-labels")
async def seed_decision_minority_label_queue(
    background_tasks: BackgroundTasks,
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    limit: int = 80,
    confidence_threshold: float = 0.72,
):
    try:
        result = seed_decision_minority_label_review_queue(
            workspace_name=workspace_name,
            limit=limit,
            confidence_threshold=confidence_threshold,
        )
        _schedule_review_prescreen(background_tasks, workspace_name, int(result.get("inserted") or 0))
        return {
            "message": "Decision minority-label review seeds queued",
            "prescreen_status": "scheduled",
            **result,
        }
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
