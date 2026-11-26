#!/usr/bin/env bash
# Usage: scripts/dev/start-service.sh <service>
# Runs one service in the foreground on its slot port (uvicorn on 127.0.0.1).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=scripts/dev/ports.sh
source "$root/scripts/dev/ports.sh"

service="${1:-}"
if [ -z "$service" ] || [ ! -d "$root/services/$service" ]; then
  echo "usage: $0 <pipeline-runner|artifact-store|release-service|dashboard>" >&2
  exit 2
fi
port="$(service_port "$service")"
mkdir -p "$SHIPYARD_DATA_DIR"
cd "$root/services/$service"
exec uv run --locked uvicorn app.main:app --host 127.0.0.1 --port "$port"
