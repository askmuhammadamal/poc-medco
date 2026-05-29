#!/usr/bin/env bash
# batam-poc — one-command launcher for macOS / Linux.
#
#   ./start.sh                              # bundled simulator + dashboard
#   PLC_HOST=192.168.1.50 ./start.sh        # real PLC over TCP (PLC_PORT default 502)
#   PLC_HOST=10.0.0.5 PLC_PORT=502 PLC_UNIT=1 ./start.sh
#   ALLOW_WRITES=1 ./start.sh               # enable writes (DANGER: reaches hardware)
#   NO_BROWSER=1 ./start.sh                 # don't auto-open the browser
#
# Creates the venvs + installs deps on first run, starts the simulator (unless PLC_HOST is set)
# and the middleware service, then opens the dashboard. Ctrl-C stops everything it started.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM="$ROOT/plc-simulator"
MW="$ROOT/middleware"
SIMPY="$SIM/.venv/bin/python"
MWPY="$MW/.venv/bin/python"

PLC_HOST="${PLC_HOST:-}"
PLC_PORT="${PLC_PORT:-502}"
PLC_UNIT="${PLC_UNIT:-1}"

need_python() { command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found. Install Python 3.9+."; exit 1; }; }

ensure_venv() { # dir, pip-args...
    local dir="$1"; shift
    if [ ! -x "$dir/.venv/bin/python" ]; then
        echo "==> First run: setting up venv in $(basename "$dir") ..."
        (cd "$dir" && python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q "$@")
    fi
}

open_browser() {
    [ -n "${NO_BROWSER:-}" ] && return 0
    if command -v open >/dev/null 2>&1; then open "$1" >/dev/null 2>&1 || true
    elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$1" >/dev/null 2>&1 || true
    fi
}

need_python
ensure_venv "$SIM" -r requirements.txt
ensure_venv "$MW" -e ".[dev]"

PIDS=()
cleanup() { echo; echo "Stopping..."; for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup INT TERM EXIT

SVC_ARGS=(--mode scan)
if [ -z "$PLC_HOST" ]; then
    echo "==> Starting simulator on :5020 ..."
    (cd "$SIM" && exec "$SIMPY" plc_sim.py --mode known) &
    PIDS+=($!)
    sleep 3
else
    SVC_ARGS+=(--host "$PLC_HOST" --port "$PLC_PORT" --unit "$PLC_UNIT")
    echo "==> Target PLC: $PLC_HOST:$PLC_PORT unit $PLC_UNIT"
fi
[ -n "${ALLOW_WRITES:-}" ] && SVC_ARGS+=(--allow-writes)

echo "==> Starting middleware service on :8000 ..."
(cd "$MW" && exec "$MWPY" -m driftwatch "${SVC_ARGS[@]}") &
PIDS+=($!)

sleep 4
echo
echo "  Dashboard: http://127.0.0.1:8000"
[ -z "$PLC_HOST" ] && echo "  Source:    built-in simulator (:5020)" || echo "  Source:    $PLC_HOST:$PLC_PORT unit $PLC_UNIT"
if [ -n "${ALLOW_WRITES:-}" ]; then echo "  Writes:    ENABLED (reaches hardware)"; else echo "  Writes:    disabled"; fi
echo "  Ctrl-C to stop."
open_browser "http://127.0.0.1:8000"

wait
