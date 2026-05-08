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
echo "Attempting to start control worker..."
# Use nohup to run the control worker as a detached process
# 使用 nohup 将控制台 worker 作为独立进程运行
nohup "$PYTHON_BIN" -m addressforge.control.worker "$@" > "$ROOT_DIR/worker.log" 2>&1 &
echo $! > "$ROOT_DIR/worker.pid"
echo "Control worker started with PID $(cat "$ROOT_DIR/worker.pid")"
