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

echo "[1/4] Freezing Gold Labels..."
# Use Python directly to avoid dependency on a running API server
python3 -c "from addressforge.learning.gold import freeze_gold_set; freeze_gold_set('default', notes='Evolution cycle auto-freeze')"

echo "[2/4] Training Reranker Model..."
python3 "$ROOT_DIR/scripts/train_reranker_model.py"
mkdir -p "$ROOT_DIR/addressforge/runtime/models/"
cp "$ROOT_DIR/runtime/models/reranker_catboost_v1.cbm" "$ROOT_DIR/addressforge/runtime/models/"

echo "[3/4] Training Decision Model..."
python3 "$ROOT_DIR/scripts/train_decision_model.py"
cp "$ROOT_DIR/runtime/models/decision_catboost_v1.cbm" "$ROOT_DIR/addressforge/runtime/models/"

echo "[4/4] Restarting Services to Apply New Models..."
"$ROOT_DIR/scripts/run_all.sh"

echo "--- Evolution Cycle Completed ---"
