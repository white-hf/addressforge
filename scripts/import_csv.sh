#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

if [ -z "${ADDRESSFORGE_IMPORT_CSV_PATH:-}" ]; then
  echo "ADDRESSFORGE_IMPORT_CSV_PATH is required" >&2
  exit 1
fi

cd "$ROOT_DIR"
exec "$PYTHON_BIN" -m addressforge.pipelines.import_csv
