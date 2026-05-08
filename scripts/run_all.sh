#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Stopping all existing AddressForge services..."
ps aux | grep -E "addressforge.console.server|addressforge.control.worker" | grep -v grep | awk '{print $2}' | xargs kill || true

echo "Starting Console..."
"$ROOT_DIR/scripts/run_console.sh" > "$ROOT_DIR/console.log" 2>&1 &
CONSOLE_PID=$!
echo "Console PID: $CONSOLE_PID"

echo "Starting Worker..."
"$ROOT_DIR/scripts/run_control_worker.sh" > "$ROOT_DIR/worker.log" 2>&1 &
WORKER_PID=$!
echo "Worker PID: $WORKER_PID"

echo "Waiting for services to initialize (5 seconds)..."
sleep 5

echo "--- Verifying Service Status ---"

echo "Checking process status:"
ps aux | grep -E "addressforge.console.server|addressforge.control.worker" | grep -v grep || { echo "ERROR: One or more services failed to start!"; exit 1; }

echo "--- Console Log ---"
tail -n 10 "$ROOT_DIR/console.log"

echo "--- Worker Log ---"
tail -n 10 "$ROOT_DIR/worker.log"

echo "--- HTTP Health Check ---"
curl_output=$(curl -s http://127.0.0.1:8011/health)
if [ "$curl_output" == "ok" ]; then
    echo "Console health check: OK"
else
    echo "ERROR: Console health check FAILED. Output: $curl_output"
    exit 1
fi

echo "--- All services successfully started and healthy! ---"
