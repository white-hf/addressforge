from __future__ import annotations

import os
import datetime
import subprocess
import sys
from typing import Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.control import (
    bootstrap_control_center,
    count_jobs,
    count_jobs_by_kind,
    count_cleaning_results,
    count_available_for_review,
    create_job,
    get_job_details,
    get_ingestion_runtime_config,
    get_setting,
    list_jobs,
    list_settings,
    seed_settings_from_env,
    set_setting,
    summarize_latest_ingestion_cleaning_batch,
    _truthy_setting,
    update_ingestion_runtime_config,
)
from addressforge.models import (
    get_workspace,
    list_models,
    list_workspaces,
    ensure_workspace,
)
from addressforge.learning import count_active_learning_queue, count_gold_labels
from addressforge.services.business_service import get_business_dashboard_metrics, get_asset_stats

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


@app.on_event("startup")
async def on_startup():
    """
    Seeds environment settings into the database as defaults on startup.
    启动时将环境设置填充到数据库中作为默认值。
    """
    try:
        seed_settings_from_env()
    except Exception as exc:
        print(f"WARNING: Failed to seed settings from environment: {exc}")

def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class IngestionApiConfigPayload(BaseModel):
    batch_size: int | None = None


class IngestionDbConfigPayload(BaseModel):
    batch_size: int | None = None
    table: str | None = None
    cursor_column: str | None = None
    tiebreaker_column: str | None = None
    external_id_column: str | None = None
    raw_address_column: str | None = None
    city_column: str | None = None
    province_column: str | None = None
    postal_code_column: str | None = None
    latitude_column: str | None = None
    longitude_column: str | None = None


class IngestionConfigPayload(BaseModel):
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME
    mode: str = "api"
    source_name: str | None = None
    api: IngestionApiConfigPayload | None = None
    db: IngestionDbConfigPayload | None = None

class EnvConfigPayload(BaseModel):
    TELEGRAM_BOT_TOKEN: str | None = None
    API_TOKEN: str | None = None
    SALT: str | None = None
    MYSQL_HOST: str | None = None
    MYSQL_USER: str | None = None
    MYSQL_PASSWORD: str | None = None
    MYSQL_DATABASE: str | None = None
    AGENT_API_BASE_URL: str | None = None
    ADDRESSFORGE_INGESTION_BATCH_LIST_OVERRIDE: str | None = None
    ADDRESSFORGE_PORT: int | None = None
    ADDRESSFORGE_CONSOLE_PORT: int | None = None


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"

@app.get("/api/v1/control/status")
async def control_status(workspace_name: str = Query(default=ADDRESSFORGE_WORKSPACE_NAME)) -> dict[str, Any]:
    """
    Returns system status summary including worker liveness and recent background jobs.
    返回系统状态汇总，包括 worker 活跃度及最近的后台任务。
    """
    snapshot = bootstrap_control_center()
    target_workspace = workspace_name or snapshot["workspace"].get("workspace_name") or ADDRESSFORGE_WORKSPACE_NAME
    
    # Check Worker Liveness
    # 检查 Worker 活跃度
    last_seen_str = get_setting(target_workspace, "worker.global.last_seen", None)
    is_worker_active = False
    if last_seen_str:
        try:
            last_seen = datetime.datetime.strptime(str(last_seen_str)[:19], "%Y-%m-%d %H:%M:%S")
            # If last seen within 30 seconds, consider it alive
            if (datetime.datetime.now() - last_seen).total_seconds() < 30:
                is_worker_active = True
        except Exception:
            pass

    return {
        "workspace_name": target_workspace,
        "is_worker_active": is_worker_active,
        "workspace": get_workspace(target_workspace),
        "metrics": get_business_dashboard_metrics(target_workspace),
        "assets": get_asset_stats(target_workspace),
        "raw_record_count": count_cleaning_results(target_workspace),
        "gold_labels": {
            "accepted_human": count_gold_labels(target_workspace, review_status="accepted", label_source="human"),
            "pending_human": count_gold_labels(target_workspace, review_status="pending", label_source="human"),
            "rejected_human": count_gold_labels(target_workspace, review_status="rejected", label_source="human"),
        },
        "active_learning": {
            "queued": count_active_learning_queue(target_workspace, status="queued"),
            "accepted_total": count_cleaning_results(target_workspace, decision="accept"),
            "available_total": count_available_for_review(target_workspace),
        },
        "job_counts": count_jobs(target_workspace),
        "job_kind_counts": count_jobs_by_kind(target_workspace),
        "recent_jobs": list_jobs(target_workspace, limit=10),
        "has_shadow_model": Path("runtime/models/decision_catboost_v1.cbm").exists(),
        "has_reranker_model": Path("runtime/models/reranker_catboost_v1.cbm").exists(),
        "continuous_mode": {
            "is_enabled": _truthy_setting(get_setting(target_workspace, "continuous_mode.enabled", False)),
            "interval_seconds": int(get_setting(target_workspace, "continuous_mode.interval_seconds", 300) or 300),
            "last_trigger_at": get_setting(target_workspace, "continuous_mode.last_trigger_at", None),
        }
    }


@app.get("/api/v1/control/env")
async def get_env_config(workspace_name: str = Query(default=ADDRESSFORGE_WORKSPACE_NAME)) -> dict[str, Any]:
    """
    Reads the environment configuration from .env.local and database settings.
    从 .env.local 文件和数据库设置中读取环境配置。
    """
    env_file = BASE_DIR.parent / ".env.local"
    if not env_file.exists():
        env_file = BASE_DIR / ".env.local"
    
    file_config = {}
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, val = line.split("=", 1)
                        file_config[key.strip()] = val.strip().strip('"\'')
    
    return {
        "env_config": {
            "TELEGRAM_BOT_TOKEN": get_setting(workspace_name, "env.TELEGRAM_BOT_TOKEN", file_config.get("TELEGRAM_BOT_TOKEN", "")),
            "API_TOKEN": get_setting(workspace_name, "env.API_TOKEN", file_config.get("API_TOKEN", "")),
            "SALT": get_setting(workspace_name, "env.SALT", file_config.get("SALT", "")),
            "MYSQL_HOST": get_setting(workspace_name, "env.MYSQL_HOST", file_config.get("MYSQL_HOST", "localhost")),
            "MYSQL_USER": get_setting(workspace_name, "env.MYSQL_USER", file_config.get("MYSQL_USER", "root")),
            "MYSQL_PASSWORD": get_setting(workspace_name, "env.MYSQL_PASSWORD", file_config.get("MYSQL_PASSWORD", "")),
            "MYSQL_DATABASE": get_setting(workspace_name, "env.MYSQL_DATABASE", file_config.get("MYSQL_DATABASE", "addressforge")),
            "AGENT_API_BASE_URL": get_setting(workspace_name, "env.AGENT_API_BASE_URL", file_config.get("AGENT_API_BASE_URL", "http://localhost:9000")),
            "ADDRESSFORGE_INGESTION_BATCH_LIST_OVERRIDE": get_setting(workspace_name, "env.ADDRESSFORGE_INGESTION_BATCH_LIST_OVERRIDE", file_config.get("ADDRESSFORGE_INGESTION_BATCH_LIST_OVERRIDE", "")),
            "ADDRESSFORGE_PORT": int(get_setting(workspace_name, "env.ADDRESSFORGE_PORT", file_config.get("ADDRESSFORGE_PORT", 8010))),
            "ADDRESSFORGE_CONSOLE_PORT": int(get_setting(workspace_name, "env.ADDRESSFORGE_CONSOLE_PORT", file_config.get("ADDRESSFORGE_CONSOLE_PORT", 8011))),
        }
    }


@app.post("/api/v1/control/env")
async def update_env_config(payload: EnvConfigPayload, workspace_name: str = Query(default=ADDRESSFORGE_WORKSPACE_NAME)) -> dict[str, Any]:
    """
    Updates the environment configuration in .env.local and database.
    在 .env.local 文件和数据库中更新环境配置。
    """
    # 1. Update Database settings
    # 1. 更新数据库设置
    updates = payload.model_dump(exclude_none=True)
    for key, val in updates.items():
        set_setting(workspace_name, f"env.{key}", val)

    # 2. Update .env.local file
    # 2. 更新 .env.local 文件
    env_file = BASE_DIR.parent / ".env.local"
    if not env_file.exists():
        env_file = BASE_DIR / ".env.local"
        
    lines = []
    keys_found = set()
    
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, val = stripped.split("=", 1)
                    key = key.strip()
                    if key in updates:
                        # Replace the value
                        # 替换值
                        lines.append(f'{key}="{updates[key]}"\n')
                        keys_found.add(key)
                        continue
                lines.append(line)
                
    # Add new keys
    # 添加新键
    for key, val in updates.items():
        if key not in keys_found:
            lines.append(f'{key}="{val}"\n')
            
    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(lines)
        
    return {
        "status": "updated",
        "message": "Environment config updated in DB and .env.local. Restart required for system-wide effect."
    }


@app.get("/api/v1/control/ingestion-config")
async def get_ingestion_config(workspace_name: str = Query(default=ADDRESSFORGE_WORKSPACE_NAME)) -> dict[str, Any]:
    return {
        "workspace_name": workspace_name,
        "ingestion_config": get_ingestion_runtime_config(workspace_name),
    }


@app.post("/api/v1/control/ingestion-config")
async def update_ingestion_config(payload: IngestionConfigPayload) -> dict[str, Any]:
    try:
        updated = update_ingestion_runtime_config(
            payload.workspace_name,
            {
                "mode": payload.mode,
                "source_name": payload.source_name,
                "api": payload.api.model_dump(exclude_none=True) if payload.api else {},
                "db": payload.db.model_dump(exclude_none=True) if payload.db else {},
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "status": "updated",
        "workspace_name": payload.workspace_name,
        "ingestion_config": updated,
    }


@app.post("/api/v1/control/worker/start")
async def start_worker():
    """
    Spawns the background worker process automatically.
    自动产生后台 worker 进程。
    """
    # Path to the official startup script
    # 官方启动脚本的路径
    script_path = BASE_DIR / "scripts" / "run_control_worker.sh"
    
    if not script_path.exists():
        raise HTTPException(status_code=500, detail=f"Startup script not found at {script_path}")

    try:
        # Start the worker in a detached background process
        # 在独立的后台进程中启动 worker
        process = subprocess.Popen(
            [str(script_path)],
            stdout=open(BASE_DIR / "worker.log", "a"),
            stderr=subprocess.STDOUT,
            preexec_fn=os.setpgrp, # Detach from parent
            env={**os.environ, "PYTHONPATH": str(BASE_DIR / "src")}
        )
        return {"status": "starting", "pid": process.pid}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to launch worker: {str(exc)}")


# Template Routes
@app.get("/batch", response_class=HTMLResponse)
async def batch_page(request: Request):
    return templates.TemplateResponse(request=request, name="batch.html", context={"active": "batch", "title": "Batch Management"})

@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    return templates.TemplateResponse(request=request, name="reports.html", context={"active": "reports", "title": "Reports Center"})

@app.get("/assets", response_class=HTMLResponse)
async def assets_page(request: Request):
    """
    Renders the Data Assets & Gold Library page.
    渲染资产与金标库页面。
    """
    return templates.TemplateResponse(request=request, name="assets.html", context={"active": "assets", "title": "Data Assets & Gold Library"})

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """
    Renders the System Settings page.
    渲染系统设置页面。
    """
    return templates.TemplateResponse(request=request, name="settings.html", context={"active": "settings", "title": "System Settings"})

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
