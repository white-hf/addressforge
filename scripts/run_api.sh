#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Auto-activate virtual environment if it exists
# 如果存在虚拟环境，则自动激活
VENV_PYTHON_BIN=""
if [ -f "$ROOT_DIR/.venv/bin/activate" ]; then
    source "$ROOT_DIR/.venv/bin/activate"
    VENV_PYTHON_BIN="$ROOT_DIR/.venv/bin/python" # Explicitly use venv python
fi
PYTHON_BIN="${VENV_PYTHON_BIN:-python3}" # Fallback to system python3

export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

cd "$ROOT_DIR"
exec "$PYTHON_BIN" -m addressforge.api.server
