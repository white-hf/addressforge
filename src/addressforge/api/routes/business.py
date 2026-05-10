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

from addressforge.services.asset_service import get_asset_stats, generate_asset_quality_report

@router.get("/asset-stats")
async def asset_stats(workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME):
    """
    Returns statistics about canonical building and unit assets.
    返回关于标准建筑与单元资产的统计信息。
    """
    return get_asset_stats(workspace_name)


@router.get("/asset-quality")
async def asset_quality(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME, 
    confidence_threshold: float = 0.85,
    source_name: str | None = None
):
    """
    Returns canonical/reference asset quality diagnostics and generates a report.
    Can be filtered by source_name for fresh-data analysis.
    返回标准资产/参考融合质量诊断并生成报表。可以按 source_name 过滤以进行新数据分析。
    """
    return generate_asset_quality_report(workspace_name, confidence_threshold, source_name)

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

@router.get("/reports/view/{report_type}")
async def view_report(report_type: str):
    """
    Returns the latest report of a specific type wrapped in HTML for viewing.
    返回包装在 HTML 中以便查看的特定类型的最新报表。
    """
    from fastapi.responses import HTMLResponse
    report_dir = Path("runtime/reports")
    
    # Map report types to file patterns
    # 将报表类型映射到文件模式
    pattern_map = {
        "quality": "*quality*.md",
        "evaluation": "*release_report.md",
        "gold_governance": "*gold_governance*.md",
        "shadow": "*shadow_report.md"
    }
    
    if report_type not in pattern_map:
        raise HTTPException(status_code=400, detail="Invalid report type / 无效的报表类型")
        
    pattern = pattern_map[report_type]
    files = list(report_dir.glob(pattern))
    
    if not files:
        raise HTTPException(status_code=404, detail=f"No {report_type} report found / 未找到 {report_type} 报表")
        
    latest_file = max(files, key=lambda f: f.stat().st_mtime)
    content = latest_file.read_text(encoding="utf-8")
    
    # Wrap in simple HTML for display
    # 包装在简单的 HTML 中进行显示
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <title>{report_type.replace('_', ' ').title()} Report</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding: 40px; line-height: 1.6; color: #333; max-width: 900px; margin: 0 auto; }}
            pre {{ background: #f8fafc; padding: 20px; border-radius: 12px; overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; border: 1px solid #e2e8f0; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 14px; }}
        </style>
    </head>
    <body>
        <pre>{content}</pre>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

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

from addressforge.learning.gold import list_gold_labels, update_gold_label

@router.get("/gold-labels")
async def get_gold_labels(
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
    q: str | None = None,
    limit: int = 50,
):
    """
    Lists gold labels with optional search query.
    列出带有可选搜索查询的金标。
    """
    return list_gold_labels(workspace_name, search_query=q, limit=limit)

@router.patch("/gold-labels/{gold_label_id}")
async def patch_gold_label(
    gold_label_id: int,
    data: dict,
    workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME,
):
    """
    Updates specific fields of a gold label (e.g., for manual correction).
    更新金标的特定字段 (例如用于手动修正)。
    """
    success = update_gold_label(
        workspace_name=workspace_name,
        gold_label_id=gold_label_id,
        building_type=data.get("building_type"),
        suggested_unit_number=data.get("suggested_unit_number"),
    )
    if not success:
        raise HTTPException(status_code=404, detail="Gold label not found or update failed")
    return {"status": "ok"}
