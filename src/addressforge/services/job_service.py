from addressforge.control import create_job, get_job_details, list_jobs
from addressforge.core.common import dumps_payload, fetch_all
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.core.utils import logger

def enqueue_job(workspace_name: str, job_kind: str, payload: dict, requested_by: str = None, priority: int = 0):
    """
    Enqueues a new background job with duplicate suppression.
    将新的后台任务入队，并进行重复抑制。
    """
    # 1. Check for existing active jobs of the same kind to prevent redundant execution
    # 1. 检查是否存在同类型的活动任务，以防止冗余执行
    active_jobs = fetch_all(
        "SELECT job_id FROM control_job WHERE workspace_name = %s AND job_kind = %s AND status IN ('queued', 'running') LIMIT 1",
        (workspace_name or ADDRESSFORGE_WORKSPACE_NAME, job_kind)
    )
    if active_jobs:
        logger.warning("Suppressed duplicate job request: %s is already active (Job ID: %s)", job_kind, active_jobs[0]["job_id"])
        raise ValueError(f"Duplicate suppressed: A {job_kind} job is already active.")

    return create_job(
        workspace_name=workspace_name or ADDRESSFORGE_WORKSPACE_NAME,
        job_kind=job_kind,
        payload=payload,
        requested_by=requested_by,
        priority=priority,
    )

def fetch_job_status(job_id: int):
    return get_job_details(job_id)

def fetch_jobs(workspace_name: str, status: str = None, job_kind: str = None, limit: int = 20):
    return list_jobs(workspace_name, status=status, job_kind=job_kind, limit=limit)
