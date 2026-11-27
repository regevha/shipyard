# Shipyard demo (wave 2)

Four services on your machine, plain uvicorn processes on 127.0.0.1, one SQLite file each:
pipeline-runner, artifact-store, release-service and the dashboard (read-only web page). The ports
come from a slot number: port = 18000 + 10 x `SHIPYARD_SLOT` + service index (0 pipeline-runner,
1 artifact-store, 2 release-service, 3 dashboard). Slot 0 gives 18000-18003. Needs `uv`, `bash`,
`curl` and `python3`.

## Run it

From the repository root:

```bash
SHIPYARD_SLOT=0 scripts/dev/start-stack.sh
```

Then open the dashboard at http://127.0.0.1:18003/ (slot N: `http://127.0.0.1:<18003 + 10 x N>/`).
The page refreshes every 5 s. Logs and pid files are in `/tmp/shipyard/slot<N>/`.

Stop everything with:

```bash
SHIPYARD_SLOT=0 scripts/dev/stop-stack.sh
```

Starting again wipes the slot's data (`/tmp/shipyard/slot<N>`), so every start is a clean demo.

## Walkthrough

About five minutes. Copy the block below into a terminal at the repository root (or save it and
run `SHIPYARD_SLOT=0 bash -euo pipefail demo.sh`). It starts the stack itself and leaves it running;
keep the dashboard open in a browser next to the terminal; no need to reload, the page refreshes on
its own. Each `>>>` line says what to look at, and the script then waits 6 s so the page catches up
(`DEMO_PAUSE=0` skips the waits).

```sh
SLOT="${SHIPYARD_SLOT:-0}"
RUNNER="http://127.0.0.1:$((18000 + 10 * SLOT))"
STORE="http://127.0.0.1:$((18001 + 10 * SLOT))"
RELEASES="http://127.0.0.1:$((18002 + 10 * SLOT))"
DASH="http://127.0.0.1:$((18003 + 10 * SLOT))"

# look MESSAGE: say what to look at in the browser, then give the page time to refresh.
look() { echo ">>> $1"; sleep "${DEMO_PAUSE:-6}"; }
# json FIELD: print one top-level field of the JSON on stdin.
json() { python3 -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"; }
# wait_run BUILD_ID: poll the runner until the run is no longer running, print its status.
wait_run() {
  for _ in $(seq 1 120); do
    status="$(curl -fsS "$RUNNER/runs/$1" | json status)"
    [ "$status" != running ] && { echo "$status"; return 0; }
    sleep 0.5
  done
  echo "run $1 did not finish" >&2
  return 1
}

# 1. Start the stack (stops and wipes this slot first).
scripts/dev/start-stack.sh
look "open $DASH/ : four empty sections (Builds, Failures, Artifacts, Releases)"

# 2. A passing pipeline: two steps, 0.5 s each, then one fake artifact upload.
PASS_ID="$(curl -fsS -X POST "$RUNNER/runs" -H 'content-type: application/json' -d '{
  "name": "shipyard-api",
  "steps": [
    {"name": "install", "command": "pip install -r requirements.txt"},
    {"name": "test", "command": "pytest"}
  ]}' | json build_id)"
echo "passing build $PASS_ID: $(wait_run "$PASS_ID")"
curl -fsS "$RUNNER/runs/$PASS_ID"; echo
look "dashboard Builds: shipyard-api passed, both steps passed; Artifacts: shipyard-api v1"

# 3. A failing pipeline: the step whose command is exactly "fail" fails, the rest is skipped.
FAIL_ID="$(curl -fsS -X POST "$RUNNER/runs" -H 'content-type: application/json' -d '{
  "name": "shipyard-web",
  "steps": [
    {"name": "install", "command": "npm ci"},
    {"name": "test", "command": "fail"},
    {"name": "package", "command": "npm run build"}
  ]}' | json build_id)"
echo "failing build $FAIL_ID: $(wait_run "$FAIL_ID")"
curl -fsS "$RUNNER/runs/$FAIL_ID"; echo
look "dashboard Failures: shipyard-web, failure 'step \"test\" failed'; no new artifact"

# 4. The artifact the passing build uploaded: download it and check its SHA-256.
#    Scratch files go to the slot's data dir, which the next start wipes.
SCRATCH="/tmp/shipyard/slot$SLOT"
mkdir -p "$SCRATCH"
curl -fsS -D "$SCRATCH/demo-headers.txt" -o "$SCRATCH/demo-artifact.bin" \
  "$STORE/artifacts/shipyard-api/versions/1"
python3 - "$SCRATCH" <<'PY'
import hashlib
import sys

scratch = sys.argv[1]
body = open(f"{scratch}/demo-artifact.bin", "rb").read()
headers = dict(
    line.split(": ", 1) for line in open(f"{scratch}/demo-headers.txt").read().splitlines() if ": " in line
)
sent = {k.lower(): v for k, v in headers.items()}["x-checksum-sha256"]
assert hashlib.sha256(body).hexdigest() == sent, "checksum mismatch"
print(f"artifact shipyard-api v1: {body!r}, checksum {sent} matches")
PY

# 5. Request a release of shipyard-api v1, approve it, promote it (twice: same answer).
REL_ID="$(curl -fsS -X POST "$RELEASES/releases" -H 'content-type: application/json' \
  -d '{"artifact": {"name": "shipyard-api", "version": 1}, "requested_by": "sam"}' | json release_id)"
echo "release $REL_ID requested by sam"
look "dashboard Releases: shipyard-api v1, pending, requested by sam"
curl -fsS -X POST "$RELEASES/releases/$REL_ID/decision" -H 'content-type: application/json' \
  -d '{"decision": "approved", "decided_by": "dana"}'; echo
look "dashboard Releases: now approved, decided by dana"
curl -fsS -X POST "$RELEASES/releases/$REL_ID/promote"; echo
curl -fsS -X POST "$RELEASES/releases/$REL_ID/promote"; echo
echo "(the second promote answers 200 with the same promoted_at; the dashboard shows no promotion)"

# 6. A promote of a release that is not approved is refused with 409.
PENDING_ID="$(curl -fsS -X POST "$RELEASES/releases" -H 'content-type: application/json' \
  -d '{"artifact": {"name": "shipyard-api", "version": 1}, "requested_by": "lee"}' | json release_id)"
code="$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$RELEASES/releases/$PENDING_ID/promote")"
echo "promote of a pending release: HTTP $code (expected 409)"
[ "$code" = 409 ]

# 7. What the dashboard page reads: its own JSON API (events from the three other services).
sleep 1
curl -fsS "$DASH/builds"; echo
curl -fsS "$DASH/builds?status=failed"; echo
curl -fsS "$DASH/artifacts"; echo
curl -fsS "$DASH/releases"; echo
python3 - "$DASH" "$PASS_ID" "$FAIL_ID" "$REL_ID" <<'PY'
import json
import sys
import urllib.request

dash, pass_id, fail_id, rel_id = sys.argv[1:]
get = lambda path: json.load(urllib.request.urlopen(dash + path))["items"]  # noqa: E731
builds = {b["build_id"]: b["status"] for b in get("/builds")}
assert builds == {pass_id: "passed", fail_id: "failed"}, builds
assert [a["build_id"] for a in get("/artifacts")] == [pass_id]
release = next(r for r in get("/releases") if r["release_id"] == rel_id)
assert (release["status"], release["requested_by"], release["decided_by"]) == ("approved", "sam", "dana")
print("dashboard API: 2 builds (passed, failed), 1 artifact, release approved by dana")
PY
echo ">>> done; the stack keeps running. Stop it with: SHIPYARD_SLOT=$SLOT scripts/dev/stop-stack.sh"
```

What you saw: the runner faked two steps per build (a command of exactly `fail` fails), uploaded one
artifact for the passing build only, the store checksummed it, the release went pending, approved
and promoted, and the dashboard built its four views from the events the services posted to it.

## Known limitations

- No authentication between services or for clients (Q-09): anyone who can reach a port can start
  runs, post events to the dashboard or approve and promote releases. Wave 3.
- SQLite data is throw-away: every `start-stack.sh` wipes the slot's data dir.
- Steps are simulated (Q-19, Q-33): commands are never executed; exactly `fail` fails, anything
  else passes.
- One fake artifact per passed build, named after the pipeline (Q-34); a build with a failed step
  uploads nothing.
- No retries of the upload (Q-36, #120): one failed or timed-out attempt (timeout 10 s) fails the
  build with `artifact upload failed`.
- Events are plain HTTP calls, no queue until wave 3 (Q-27): senders try up to three times within
  5 s, then drop the event, so the dashboard can miss an event when it is down. A dashboard that
  hangs loses the events sent meanwhile (dropped after 5 s, no queue until wave 3); it no longer
  delays other requests to the services that send them (#171, Q-42).
- pipeline-runner's simulated steps and its artifact upload still run on its request-handler
  threads, so under load they can delay its other requests (Q-42 follow-up, the project owner;
  they move off those threads with the queue in wave 3).
- An unexpected error inside a run fails the build with reason `internal error` (#167, Q-41):
  `failed_step` is null, the step that was running (if any) is failed and the steps after it are
  skipped.
- release-service does not check that the artifact exists (Q-16): you can request, approve and
  promote a name and version that was never built or uploaded.
- The dashboard has no buttons and shows no promotion (Q-32, Q-14): decide and promote with curl on
  release-service.
- A failed build can still show an artifact (#131, option (a), decided by the project owner): when the upload
  times out after the store saved the bytes, the build fails but the artifact stays listed.
- No request size caps on the runner, release-service or the dashboard's `POST /events` (#163,
  Q-39): wave 3. Only artifact-store limits uploads (100 MiB).
- Artifact versions go up to 2^63-1 (9223372036854775807); a larger version is refused with 422
  everywhere a version is received (Q-40).
- The dashboard page shows at most 200 items per section (no paging UI).
- Rare cases are ignored until the end of wave 3 (the project owner, Q-41 follow-up): for example,
  if even the write that marks a crashed run failed is refused (the database is gone), the run
  stays `running`.
