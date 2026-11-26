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

for service in "${SHIPYARD_SERVICES[@]}"; do
  port="$(service_port "$service")"
  (
    cd "$root/services/$service"
    nohup uv run uvicorn app.main:app --host 127.0.0.1 --port "$port" \
      >"$SHIPYARD_DATA_DIR/$service.log" 2>&1 &
    echo $! >"$SHIPYARD_DATA_DIR/$service.pid"
  )
done

fail() {
  echo "error: $1" >&2
  tail -n 20 "$SHIPYARD_DATA_DIR/$2.log" >&2 || true
  "$root/scripts/dev/stop-stack.sh" || true
  exit 1
}

for service in "${SHIPYARD_SERVICES[@]}"; do
  port="$(service_port "$service")"
  ok=0
  for _ in $(seq 1 300); do
    if curl -fsS "http://127.0.0.1:$port/openapi.json" >/dev/null 2>&1; then
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
