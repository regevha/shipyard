#!/usr/bin/env bash
# Usage: SHIPYARD_SLOT=<n> scripts/dev/start-stack.sh
# Starts all four services as plain uvicorn processes on the slot's ports (127.0.0.1).
# Order (#136): stop a stack already running in the slot, refuse if a slot port is still
# in use, wipe the data dir, start, wait until every /openapi.json answers.
# Logs and pid files go to $SHIPYARD_DATA_DIR (<service>.log, <service>.pid).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=scripts/dev/ports.sh
source "$root/scripts/dev/ports.sh"

# The data dir is wiped below, so it must be this slot's dir (#149): exactly
# /tmp/shipyard/slot<SHIPYARD_SLOT>, or an override under /tmp that is neither another
# slot's dir (or inside one) nor /tmp or /tmp/shipyard themselves.
expected="/tmp/shipyard/slot${SHIPYARD_SLOT}"
data_dir="$(realpath -m -- "$SHIPYARD_DATA_DIR")"
if [ "$data_dir" != "$expected" ]; then
  case "$data_dir" in
    /tmp/shipyard/slot[0-9]*)
      echo "error: SHIPYARD_DATA_DIR=$SHIPYARD_DATA_DIR belongs to another slot than $SHIPYARD_SLOT; refusing to wipe" >&2
      exit 1
      ;;
    /tmp/shipyard | /tmp)
      echo "error: SHIPYARD_DATA_DIR=$SHIPYARD_DATA_DIR is too broad; refusing to wipe" >&2
      exit 1
      ;;
    /tmp/?*) ;;
    *)
      echo "error: SHIPYARD_DATA_DIR=$SHIPYARD_DATA_DIR is outside /tmp; refusing to wipe" >&2
      exit 1
      ;;
  esac
fi
SHIPYARD_DATA_DIR="$data_dir"
export SHIPYARD_DATA_DIR

"$root/scripts/dev/stop-stack.sh"

port_in_use() {
  python3 - "$1" <<'PY'
import socket
import sys

s = socket.socket()
try:
    s.connect(("127.0.0.1", int(sys.argv[1])))
except OSError:
    sys.exit(1)
finally:
    s.close()
PY
}

busy=0
for service in "${SHIPYARD_SERVICES[@]}"; do
  port="$(service_port "$service")"
  if port_in_use "$port"; then
    echo "error: port $port ($service, slot $SHIPYARD_SLOT) is already in use; refusing to start" >&2
    busy=1
  fi
done
[ "$busy" -eq 0 ] || exit 1

rm -rf "$SHIPYARD_DATA_DIR"
mkdir -p "$SHIPYARD_DATA_DIR"

# Every startup failure goes through fail(): message, log tail, stop what already started.
fail() {
  echo "error: $1" >&2
  tail -n 20 "$SHIPYARD_DATA_DIR/$2.log" >&2 || true
  "$root/scripts/dev/stop-stack.sh" || true
  exit 1
}

for service in "${SHIPYARD_SERVICES[@]}"; do
  port="$(service_port "$service")"
  log="$SHIPYARD_DATA_DIR/$service.log"
  # --locked: a start never rewrites uv.lock. Done in the foreground so a failure is reported.
  (cd "$root/services/$service" && uv sync --locked --quiet) >"$log" 2>&1 \
    || fail "uv sync --locked failed for $service (log tail below)" "$service"
  (
    cd "$root/services/$service"
    # The pid file holds the real server pid (the background process execs uvicorn itself,
    # no uv wrapper), so SIGKILL frees the port.
    exec nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$port" \
      >>"$log" 2>&1 &
    echo $! >"$SHIPYARD_DATA_DIR/$service.pid"
  )
done

for service in "${SHIPYARD_SERVICES[@]}"; do
  port="$(service_port "$service")"
  ok=0
  for _ in $(seq 1 300); do
    if curl -fsS --max-time 2 "http://127.0.0.1:$port/openapi.json" >/dev/null 2>&1; then
      ok=1
      break
    fi
    if ! kill -0 "$(cat "$SHIPYARD_DATA_DIR/$service.pid")" 2>/dev/null; then
      fail "$service exited before answering on port $port (log tail below)" "$service"
    fi
    sleep 0.1
  done
  [ "$ok" -eq 1 ] || fail "$service did not answer on port $port within 30 s (log tail below)" "$service"
done
echo "stack up, slot $SHIPYARD_SLOT: ports $PIPELINE_RUNNER_PORT $ARTIFACT_STORE_PORT $RELEASE_SERVICE_PORT $DASHBOARD_PORT, data $SHIPYARD_DATA_DIR"
