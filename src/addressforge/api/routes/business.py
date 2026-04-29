import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse, FileResponse
from addressforge.services.business_service import (
    get_process_overview, 
    get_business_dashboard_metrics,
    get_batch_stats,
    get_reports_list
)
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME

router = APIRouter()

@router.get("/process-overview")
async def process_overview(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME):
    return get_process_overview(workspace_name)

from addressforge.services.asset_service import get_asset_stats

@router.get("/asset-stats")
async def asset_stats(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME):
    """
    Returns statistics about canonical building and unit assets.
    返回关于标准建筑与单元资产的统计信息。
    """
    return get_asset_stats(workspace_name)

from addressforge.services.replay_service import get_release_readiness_report

@router.get("/release-readiness")
async def release_readiness(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME):
    """
    Returns a summary report for release decision making.
    返回用于发布决策的摘要报告。
    """
    return get_release_readiness_report(workspace_name)

@router.get("/dashboard-metrics")
async def dashboard_metrics(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME):
    return get_business_dashboard_metrics(workspace_name)

@router.get("/batch-stats")
async def batch_stats(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME):
    return get_batch_stats(workspace_name)

@router.get("/reports")
async def reports_list(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME):
    return get_reports_list(workspace_name)

@router.get("/reports/download")
async def download_report(path: str):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Report file not found")
    return FileResponse(path)

@router.get("/benchmark-report")
async def get_latest_benchmark_report():
    artifact_dir = Path("runtime/models")
    reports = list(artifact_dir.glob("*_eval.md"))
    if not reports:
        raise HTTPException(status_code=404, detail="No evaluation reports found")
    
    # Get the latest report by modification time
    latest_report = max(reports, key=os.path.getmtime)
    return PlainTextResponse(latest_report.read_text(encoding="utf-8"))
