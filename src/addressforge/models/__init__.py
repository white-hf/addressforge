"""Models package."""

from .registry import (
    ModelRecord,
    WorkspaceRecord,
    bootstrap_default_registry,
    ensure_default_model,
    ensure_default_workspace,
    ensure_workspace,
    deprecate_model,
    get_active_model,
    get_model,
    get_workspace,
    list_models,
    list_workspaces,
    promote_model,
    register_model_version,
)

__all__ = [
    "ModelRecord",
    "WorkspaceRecord",
    "bootstrap_default_registry",
    "ensure_default_model",
    "ensure_default_workspace",
    "ensure_workspace",
    "deprecate_model",
    "get_active_model",
    "get_model",
    "get_workspace",
    "list_models",
    "list_workspaces",
    "promote_model",
    "register_model_version",
]
