from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.models import bootstrap_default_registry, get_workspace, list_models, promote_model


app = FastAPI(title="AddressForge Console")


class PromoteModelRequest(BaseModel):
    workspace_name: str = Field(default=ADDRESSFORGE_WORKSPACE_NAME)
    model_id: int | None = None
    model_name: str | None = None
    model_version: str | None = None
    notes: str | None = None


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"


@app.get("/api/v1/workspace")
async def workspace(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME) -> dict[str, Any]:
    try:
        snapshot = bootstrap_default_registry()
        target_workspace = workspace_name or snapshot["workspace"].get("workspace_name") or ADDRESSFORGE_WORKSPACE_NAME
        workspace_row = get_workspace(target_workspace)
    except Exception:
        target_workspace = workspace_name or ADDRESSFORGE_WORKSPACE_NAME
        workspace_row = get_workspace(target_workspace)
    return {"workspace": workspace_row}


@app.get("/api/v1/models")
async def models(workspace_name: str = Query(default=ADDRESSFORGE_WORKSPACE_NAME)) -> dict[str, Any]:
    try:
        snapshot = bootstrap_default_registry()
        target_workspace = workspace_name or snapshot["workspace"].get("workspace_name") or ADDRESSFORGE_WORKSPACE_NAME
        models_list = list_models(target_workspace)
    except Exception:
        target_workspace = workspace_name or ADDRESSFORGE_WORKSPACE_NAME
        models_list = list_models(target_workspace)
    return {"workspace_name": target_workspace, "models": models_list}


@app.post("/api/v1/models/promote")
async def promote(request: PromoteModelRequest) -> dict[str, Any]:
    try:
        promoted = promote_model(
            workspace_name=request.workspace_name or ADDRESSFORGE_WORKSPACE_NAME,
            model_id=request.model_id,
            model_name=request.model_name,
            model_version=request.model_version,
            notes=request.notes,
        )
        return {"status": "ok", "model": promoted}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/")
async def root() -> dict[str, Any]:
    try:
        snapshot = bootstrap_default_registry()
    except Exception:
        snapshot = {"workspace": get_workspace(ADDRESSFORGE_WORKSPACE_NAME), "model": None}
    return {
        "name": "AddressForge Console",
        "workspace": snapshot["workspace"],
        "active_model": snapshot["model"],
        "endpoints": [
            "/health",
            "/api/v1/workspace",
            "/api/v1/models",
            "/api/v1/models/promote",
        ],
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("ADDRESSFORGE_CONSOLE_PORT", "8011"))
    uvicorn.run("addressforge.console.server:app", host="127.0.0.1", port=port, reload=False)
