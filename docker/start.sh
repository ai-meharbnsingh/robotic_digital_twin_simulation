#!/usr/bin/env bash
# ============================================================
# start.sh — Launch C++ FMS server + Python FastAPI
# ============================================================
# Runs inside the Docker container. Manages both processes
# and forwards SIGTERM/SIGINT for clean shutdown.

set -euo pipefail

# --- PIDs for cleanup ---
FMS_PID=""
API_PID=""

# --- Clean shutdown handler ---
shutdown() {
    echo "[start.sh] Received shutdown signal — stopping services..."

    if [ -n "$API_PID" ] && kill -0 "$API_PID" 2>/dev/null; then
        echo "[start.sh] Stopping Python FastAPI (PID $API_PID)..."
        kill -TERM "$API_PID" 2>/dev/null || true
        wait "$API_PID" 2>/dev/null || true
    fi

    if [ -n "$FMS_PID" ] && kill -0 "$FMS_PID" 2>/dev/null; then
        echo "[start.sh] Stopping C++ FMS server (PID $FMS_PID)..."
        kill -TERM "$FMS_PID" 2>/dev/null || true
        wait "$FMS_PID" 2>/dev/null || true
    fi

    echo "[start.sh] All services stopped."
    exit 0
}

# Trap SIGTERM and SIGINT for clean shutdown
trap shutdown SIGTERM SIGINT

# --- Resolve paths ---
APP_DIR="/app"
FMS_BINARY="${APP_DIR}/bin/fms_server"
PYTHON_APP="${APP_DIR}/python"

# --- Start C++ FMS server ---
WAREHOUSE_JSON="${APP_DIR}/configs/warehouses/${WAREHOUSE_CONFIG:-simple_grid}.json"
ROBOT_YAML="${APP_DIR}/configs/robots/${ROBOT_CONFIG:-differential_drive}.yaml"

if [ -f "$FMS_BINARY" ] && [ -x "$FMS_BINARY" ]; then
    FMS_ARGS="--tcp-port ${FMS_TCP_PORT:-65123} --rest-port ${FMS_REST_PORT:-7012}"
    if [ -f "$WAREHOUSE_JSON" ]; then
        FMS_ARGS="$FMS_ARGS --warehouse $WAREHOUSE_JSON"
    fi
    if [ -f "$ROBOT_YAML" ]; then
        FMS_ARGS="$FMS_ARGS --robot $ROBOT_YAML"
    fi
    echo "[start.sh] Starting C++ FMS server: $FMS_BINARY $FMS_ARGS"
    $FMS_BINARY $FMS_ARGS &
    FMS_PID=$!
    echo "[start.sh] C++ FMS server started (PID $FMS_PID)"
else
    echo "[start.sh] WARNING: C++ FMS binary not found at $FMS_BINARY"
    echo "[start.sh] Running in Python-only mode (API + intelligence)"
fi

# --- Start Python FastAPI ---
echo "[start.sh] Starting Python FastAPI on port ${API_PORT:-8029}..."
cd "$PYTHON_APP"
python3 -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${API_PORT:-8029}" \
    --log-level "${LOG_LEVEL:-info}" &
API_PID=$!
echo "[start.sh] Python FastAPI started (PID $API_PID)"

# --- Wait for either process to exit ---
# If either process exits, we shut down everything
echo "[start.sh] All services running."
echo "[start.sh]   API:       http://localhost:${API_PORT:-8029}"
echo "[start.sh]   Dashboard: http://localhost:${API_PORT:-8029}/dashboard"
echo "[start.sh]   Docs:      http://localhost:${API_PORT:-8029}/docs"
echo "[start.sh] Waiting..."

# Wait on both processes — if one exits, trigger shutdown
wait -n "$API_PID" ${FMS_PID:+"$FMS_PID"} 2>/dev/null || true

echo "[start.sh] A service exited — initiating shutdown..."
shutdown
