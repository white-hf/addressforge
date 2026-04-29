from addressforge.control import create_job, get_job_details, list_jobs
from addressforge.core.common import dumps_payload
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME

def enqueue_job(workspace_name: str, job_kind: str, payload: dict, requested_by: str = None, priority: int = 0):
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
