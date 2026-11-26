#!/usr/bin/env bash
# Usage: scripts/dev/stop-stack.sh
# Stops the processes named in the slot's pid files, waits for them to exit, removes the
# pid files. Exits 0 when nothing runs; a pid file whose process already exited is fine
# and is removed.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=scripts/dev/ports.sh
source "$root/scripts/dev/ports.sh"

shopt -s nullglob
for pidfile in "$SHIPYARD_DATA_DIR"/*.pid; do
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  # Only signal a live process that is really one of ours (guards against pid reuse).
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null \
    && tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null | grep -q 'uvicorn'; then
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 100); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
      for _ in $(seq 1 50); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.1
      done
    fi
  fi
  rm -f "$pidfile"
done
exit 0
