from addressforge.control import create_job
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME

def enqueue_cleaning(workspace_name, batch_size=1000, requested_by=None, notes=None):
    return create_job(
        workspace_name=workspace_name or ADDRESSFORGE_WORKSPACE_NAME,
        job_kind="cleaning_once",
        payload={"batch_size": batch_size, "notes": notes},
        requested_by=requested_by
    )
