#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Auto-activate virtual environment
if [ -f "$ROOT_DIR/.venv/bin/activate" ]; then
    source "$ROOT_DIR/.venv/bin/activate"
fi
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

echo "--- Phase 11: Starting Evolution Cycle ---"

echo "[1/5] Freezing Gold Labels..."
# Use Python directly to avoid dependency on a running API server
python3 -c "from addressforge.learning.gold import freeze_gold_set; freeze_gold_set('default', notes='Evolution cycle auto-freeze')"

echo "[2/5] Training Reranker Model..."
python3 "$ROOT_DIR/scripts/train_reranker_model.py"
mkdir -p "$ROOT_DIR/addressforge/runtime/models/"
cp "$ROOT_DIR/runtime/models/reranker_catboost_v1.cbm" "$ROOT_DIR/addressforge/runtime/models/"

echo "[3/5] Training Decision Model..."
python3 "$ROOT_DIR/scripts/train_decision_model.py"
cp "$ROOT_DIR/runtime/models/decision_catboost_v1.cbm" "$ROOT_DIR/addressforge/runtime/models/"

echo "[4/5] Training BuildingType Model..."
# Phase 17: Train BuildingType classifier
# 第 17 阶段：训练 BuildingType 分类器
python3 "$ROOT_DIR/scripts/train_building_type_model.py"
cp "$ROOT_DIR/runtime/models/building_type_catboost_v1.cbm" "$ROOT_DIR/addressforge/runtime/models/"

echo "[5/5] Hot-Reloading Models..."
# Hot-reload models via API to avoid downtime
# 通过 API 热重载模型以避免停机
curl -X POST http://127.0.0.1:8010/api/v1/models/reload -s > /dev/null || echo "API reload curl failed, but proceeding."
echo "API Server models reloaded."

# Queue a job for the worker to reload its models
# 为 worker 排队一个任务以重载其模型
python3 -c "
from addressforge.services.job_service import enqueue_job
try:
    enqueue_job('default', 'reload_models_once', {}, 'system', 0)
except ValueError as e:
    print(f'Reload job enqueue status: {e}')
"
echo "Worker model reload job handled."

echo "--- Evolution Cycle Completed ---"
