from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.control import (
    bootstrap_control_center,
    count_jobs,
    count_jobs_by_kind,
    create_job,
    get_job_details,
    get_setting,
    list_jobs,
    list_settings,
    set_setting,
)
from addressforge.models import (
    get_workspace,
    list_models,
    list_workspaces,
    ensure_workspace,
)
from addressforge.learning import count_active_learning_queue, count_gold_labels

# Resolve absolute paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

app = FastAPI(title="AddressForge Console")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Import Routers
from addressforge.api.routes.jobs import router as job_router
from addressforge.api.routes.models import router as model_router
from addressforge.api.routes.cleaning import router as cleaning_router
from addressforge.api.routes.business import router as business_router
from addressforge.api.routes.review import router as review_router

app.include_router(job_router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(model_router, prefix="/api/v1/models", tags=["models"])
app.include_router(cleaning_router, prefix="/api/v1/cleaning", tags=["cleaning"])
app.include_router(business_router, prefix="/api/v1/business", tags=["business"])
app.include_router(review_router, prefix="/api/v1/review", tags=["review"])

def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"

@app.get("/api/v1/control/status")
async def control_status(workspace_name: str = Query(default=ADDRESSFORGE_WORKSPACE_NAME)) -> dict[str, Any]:
    # 系统状态汇总接口，用于 UI 水位 Pill 渲染
    snapshot = bootstrap_control_center()
    target_workspace = workspace_name or snapshot["workspace"].get("workspace_name") or ADDRESSFORGE_WORKSPACE_NAME
    return {
        "workspace_name": target_workspace,
        "workspace": get_workspace(target_workspace),
        "gold_labels": {
            "accepted_human": count_gold_labels(target_workspace, review_status="accepted", label_source="human"),
            "pending_human": count_gold_labels(target_workspace, review_status="pending", label_source="human"),
            "rejected_human": count_gold_labels(target_workspace, review_status="rejected", label_source="human"),
        },
        "active_learning": {
            "queued": count_active_learning_queue(target_workspace, status="queued"),
        },
        "job_counts": count_jobs(target_workspace),
        "job_kind_counts": count_jobs_by_kind(target_workspace),
        "continuous_mode": {
            "enabled": _as_bool(get_setting(target_workspace, "continuous_mode.enabled", False)),
            "interval_seconds": int(get_setting(target_workspace, "continuous_mode.interval_seconds", 300) or 300),
            "last_trigger_at": get_setting(target_workspace, "continuous_mode.last_trigger_at", None),
        }
    }

# Template Routes
@app.get("/batch", response_class=HTMLResponse)
async def batch_page(request: Request):
    return templates.TemplateResponse(request=request, name="batch.html", context={"active": "batch", "title": "Batch Management"})

@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    return templates.TemplateResponse(request=request, name="reports.html", context={"active": "reports", "title": "Reports Center"})

@app.get("/review", response_class=HTMLResponse)
async def review_page(request: Request):
    return templates.TemplateResponse(request=request, name="review.html", context={"active": "review", "title": "Review Lab"})

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"active": "dashboard", "title": "Dashboard"})

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("ADDRESSFORGE_CONSOLE_PORT", "8011"))
    uvicorn.run("addressforge.console.server:app", host="127.0.0.1", port=port, reload=False)
