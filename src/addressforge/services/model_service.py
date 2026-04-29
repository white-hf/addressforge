from addressforge.models import register_model_version, promote_model, deprecate_model, list_models
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME

def register_model(workspace_name, model_name, model_version, **kwargs):
    return register_model_version(workspace_name or ADDRESSFORGE_WORKSPACE_NAME, model_name, model_version, **kwargs)

def promote(workspace_name, model_id, notes=None):
    return promote_model(workspace_name or ADDRESSFORGE_WORKSPACE_NAME, model_id=model_id, notes=notes)

def deprecate(workspace_name, model_id, notes=None):
    return deprecate_model(workspace_name or ADDRESSFORGE_WORKSPACE_NAME, model_id=model_id, notes=notes)

def fetch_models(workspace_name):
    return list_models(workspace_name or ADDRESSFORGE_WORKSPACE_NAME)
