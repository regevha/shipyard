#!/usr/bin/env bash
# Sourced by the other dev scripts. Reads SHIPYARD_SLOT (default 0) and exports the
# four ports, the base URLs, SHIPYARD_DATA_DIR and the four database URL defaults.
# Port = 18000 + 10 x slot + service index (docs/team/environment.md, Wave 2 setup).
# Inside an agent worktree (git-dir differs from git-common-dir) an explicit
# SHIPYARD_SLOT is required, because slot 0 belongs to the lead.

SHIPYARD_SERVICES=(pipeline-runner artifact-store release-service dashboard)

_ports_git_dir="$(git rev-parse --path-format=absolute --git-dir 2>/dev/null || true)"
_ports_common_dir="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
if [ -n "$_ports_git_dir" ] && [ "$_ports_git_dir" != "$_ports_common_dir" ] \
  && [ -z "${SHIPYARD_SLOT:-}" ]; then
  echo "error: inside an agent worktree SHIPYARD_SLOT must be set explicitly (slot 0 is the lead's)" >&2
  return 1 2>/dev/null || exit 1
fi
unset _ports_git_dir _ports_common_dir

SHIPYARD_SLOT="${SHIPYARD_SLOT:-0}"
case "$SHIPYARD_SLOT" in
  '' | *[!0-9]*)
    echo "error: SHIPYARD_SLOT must be a number from 0 to 99, got '$SHIPYARD_SLOT'" >&2
    return 1 2>/dev/null || exit 1
    ;;
esac
if [ "$((10#$SHIPYARD_SLOT))" -gt 99 ]; then
  echo "error: SHIPYARD_SLOT must be a number from 0 to 99, got '$SHIPYARD_SLOT'" >&2
  return 1 2>/dev/null || exit 1
fi
SHIPYARD_SLOT="$((10#$SHIPYARD_SLOT))"

PIPELINE_RUNNER_PORT=$((18000 + 10 * SHIPYARD_SLOT + 0))
ARTIFACT_STORE_PORT=$((18000 + 10 * SHIPYARD_SLOT + 1))
RELEASE_SERVICE_PORT=$((18000 + 10 * SHIPYARD_SLOT + 2))
DASHBOARD_PORT=$((18000 + 10 * SHIPYARD_SLOT + 3))

PIPELINE_RUNNER_URL="http://127.0.0.1:${PIPELINE_RUNNER_PORT}"
ARTIFACT_STORE_URL="http://127.0.0.1:${ARTIFACT_STORE_PORT}"
RELEASE_SERVICE_URL="http://127.0.0.1:${RELEASE_SERVICE_PORT}"
DASHBOARD_URL="http://127.0.0.1:${DASHBOARD_PORT}"

SHIPYARD_DATA_DIR="${SHIPYARD_DATA_DIR:-/tmp/shipyard/slot${SHIPYARD_SLOT}}"

PIPELINE_RUNNER_DATABASE_URL="${PIPELINE_RUNNER_DATABASE_URL:-sqlite:///${SHIPYARD_DATA_DIR}/pipeline_runner.db}"
ARTIFACT_STORE_DATABASE_URL="${ARTIFACT_STORE_DATABASE_URL:-sqlite:///${SHIPYARD_DATA_DIR}/artifact_store.db}"
RELEASE_SERVICE_DATABASE_URL="${RELEASE_SERVICE_DATABASE_URL:-sqlite:///${SHIPYARD_DATA_DIR}/release_service.db}"
DASHBOARD_DATABASE_URL="${DASHBOARD_DATABASE_URL:-sqlite:///${SHIPYARD_DATA_DIR}/dashboard.db}"

export SHIPYARD_SLOT SHIPYARD_DATA_DIR
export PIPELINE_RUNNER_PORT ARTIFACT_STORE_PORT RELEASE_SERVICE_PORT DASHBOARD_PORT
export PIPELINE_RUNNER_URL ARTIFACT_STORE_URL RELEASE_SERVICE_URL DASHBOARD_URL
export PIPELINE_RUNNER_DATABASE_URL ARTIFACT_STORE_DATABASE_URL
export RELEASE_SERVICE_DATABASE_URL DASHBOARD_DATABASE_URL

# service_port <service>: print the port of a service name.
service_port() {
  case "$1" in
    pipeline-runner) echo "$PIPELINE_RUNNER_PORT" ;;
    artifact-store) echo "$ARTIFACT_STORE_PORT" ;;
    release-service) echo "$RELEASE_SERVICE_PORT" ;;
    dashboard) echo "$DASHBOARD_PORT" ;;
    *) echo "error: unknown service '$1'" >&2; return 1 ;;
  esac
}
