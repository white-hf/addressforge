from addressforge.models import list_workspaces, ensure_workspace, get_workspace
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME

def fetch_all_workspaces():
    return list_workspaces()

def create_new_workspace(name, description, profile, ref_version, lang):
    return ensure_workspace(name, description, profile, ref_version, lang)

def fetch_workspace(name):
    return get_workspace(name or ADDRESSFORGE_WORKSPACE_NAME)
