# Shipyard status

Written 2026-11-27 by the project-manager after the wave 2 close-out. Base: `main` at 3456c31 (all of wave 2 merged).
Sources: the lead's verdicts and checks, `docs/PLAN.md`, the hand-offs in `docs/tasks/T020.md`..`T028.md`, `docs/DEMO.md`,
and GitHub PR and issue facts (`gh api`). Anything the project-manager inferred is marked (inferred).

## Done

Wave 2 is done (lead verdict). Every task was reviewed by the full reviewer (T027 also by the ux-reviewer), fix rounds
were verified, CI was green including `ci-ok`, and each was merged. Nothing is `unverified`: the browser checks ran in
headless Chrome. Evidence that the stack suite can fail: a mutation run in the T028 review caught a broken upload.
T027 acceptance A4 is vacuous (#173); the property it was meant to prove was verified by the reviewer by code and a
runtime request log, and the lead keeps T027 `done`.

| Task | What | PR (merge commit) | Fix rounds | Defects the review caught before merge |
| --- | --- | --- | --- | --- |
| T020 | Wave 2 plan, task specs, contract change #121 | #137 (f779826) | 1 | `StaticFiles` mounted at `/` broke the 404/405 rule; missing type stubs for strict mypy |
| T021 | Scaffold: four service projects, `stack-tests/`, dev scripts, CI matrix | #151 (92980c2) | 2 | Worktree guard keyed to the caller's cwd, so a slot-0 wipe was possible; pid file held the `uv` wrapper, so SIGKILL orphaned uvicorn; a failing `uv sync` exited silently |
| T022 | Shared error envelope and OpenAPI conformance helper | #156 (818c588) | 0 | none blocking |
| T023 | Dashboard: events intake, read API, static mount | #162 (480f8a9) | 1 | Lax type coercion (JSON `true` stored as artifact version 1); untested build.finished state-table rejections; huge offset gave 500 |
| T024 | Pipeline-runner: runs, simulated steps, fake upload, events | #164 (3d60a7f) | 1 | SQLite "database is locked" under 80-150 concurrent runs left runs `running` forever, sometimes after a 201 upload |
| T025 | Artifact-store: versioned uploads, SHA-256, 413, download, event | #161 (7ce3379) | 2 | Version above 2^63-1 gave 500; `Range` answered 206 with a whole-file checksum; file handle leaked on client disconnect |
| T026 | Release-service: request, decision, promote, events | #169 (70dde03) | 2 | Invalid JSON with a JSON content type on an unknown id gave 422, not 404; non-canonical UUID forms accepted; decision accepted `text/plain`, a CORS simple request |
| T027 | Dashboard UI: builds, failures, artifacts, releases | #168 (2fc966c) | 2 | Note text contrast 3.95:1 (UX); one long contract-legal value pushed the columns about 27,000 px off-screen |
| T028 | Stack tests, CI `stack` job, `docs/DEMO.md` | #174 (3456c31) | 0 | none in the services |

Fix round counts are from the lead's PR comments. The second fix rounds on T021, T025, T026 and T027 fixed regressions
that the verify of round 1 found (the lead's decision; `lead.md` step 5 allows one round). T028 had no fix round; the
lead applied four doc fixes in d3b39b9, and a verify APPROVE followed.

## Numbers that matter

- Services: four Python/FastAPI services on SQLite, one file each, ports 18000 + 10 x slot + service index.
- Coverage (`pytest --cov=app` on each task's merged head; from the reviewers' reports to the lead (lead-session source),
  rerun and confirmed by the closeout reviewer on main 3456c31; T022 also on PR #156, T025 also in `docs/tasks/T025.md`):
  dashboard T023 97.31% (89 tests); pipeline-runner T024 98.90% (92 tests); artifact-store T025 97.14% (73 tests);
  release-service T026 97.46% (114 tests); shared modules T022, `app/errors.py` 98% (27 tests per service).
  `fail_under = 85` in all four service `pyproject.toml` files (Q-38). T027 is static HTML/JS with no coverage tool
  (its `files_touched` allows none); its gate was the browser smoke test plus the reviewer's and ux-reviewer's browser checks.
- Stack suite: 15 tests pass (pytest "15 passed"; some functions are parametrized, e.g. the bad-name test has 6 cases).
  Tester report to the lead (lead-session source): 26.6-31 s, 5 runs; reviewer report to the lead (lead-session source):
  3 runs, 26.6-27.4 s; CI stack job per the lead (lead-session source): "15 passed in 11.55 s". `docs/tasks/T028.md` says
  about 29-31 s. Roughly 27-31 s locally, about 12 s in CI.
- 100-concurrent-run test (`test_stack_concurrency.py`): every run reaches its final state; the dashboard lists each
  build once; one artifact per passed build.
- Real-server checks: T024, 500 runs and 1002 events with 0 misses; T025, 0 misses on POST-then-GET.
- DEMO walkthrough (lead, 2026-11-27, main checkout, slot 0, `bash -euo pipefail`, `DEMO_PAUSE=0`): exit 0, last line
  `dashboard API: 2 builds (passed, failed), 1 artifact, release approved by dana`. Headless Chrome screenshot of the
  dashboard showed both builds, the failure, the artifact and both releases.

## Known limitations (from `docs/DEMO.md`)

- No authentication between services or for clients (Q-09). Wave 3.
- SQLite data is throw-away: every start wipes the slot's data dir.
- Steps are simulated (Q-19, Q-33): commands never run; exactly `fail` fails, anything else passes.
- One fake artifact per passed build, named after the pipeline (Q-34); a build with a failed step uploads nothing.
- No upload retries (Q-36, #120): one failed or timed-out attempt (10 s) fails the build with `artifact upload failed`.
- Events are plain HTTP, no queue (Q-27): three attempts, then dropped. Under load, a hanging dashboard delays other
  requests to those services (#171).
- release-service does not check that the artifact exists (Q-16).
- The dashboard has no buttons and shows no promotion (Q-32, Q-14).
- A failed build can still show an artifact (#131, Q-37).
- No request size caps on the runner, release-service or `POST /events` (#163); only artifact-store caps uploads (100 MiB).
- The dashboard answers 500 for a `release.requested` with an artifact version above 2^63-1 (#170).
- The dashboard shows at most 200 items per section (no paging UI).

## Open follow-ups

### Needs a user or contract decision

- **#163** request size caps on the runner, release-service and `POST /events`. The contracts set none. Options: (a) add
  caps to the contracts (a contract change through the lead); (b) leave them for wave 3.
- **#170** (`task`, open) dashboard answers 500 for an artifact version above 2^63-1. Options: (a) the dashboard stores
  such versions safely, no contract change; (b) the contract caps the version at 2^63-1, so release-service and
  artifact-store reject larger ones (contract change); (c) keep as is and list it as a limitation.
- **#167** (deferred) the runner has no error state for an unexpected background failure. "The run stays `running`" is
  from the T024 review (the agent's open question 2 and reviewer B1). Options: (a) a new state in the contract; (b) fail the
  run in code without a state change. Option (b) may still need a contract change, because `Run` and `BuildFinishedData`
  require `failed_step` or `failure_reason`, so a failed build needs one of them.
- **#171** (deferred) event senders block the handler thread pool when the dashboard hangs; under load this delays other
  requests to those services, which breaks the PLAN convention that events never delay a response. Options: (a) send
  events with an async client and drop after the deadline; (b) keep and accept the limitation. Behaviour choice, the
  user's to confirm.
- Not a new issue: Q-09 (auth), a React dashboard and retries (#131) are wave 3 decisions already in `docs/PLAN.md`.

### Open issues labelled `task` (not yet closed; the lead decides)

- #173 T027 acceptance A4 passes vacuously (the fetch-literal grep matches nothing). The lead keeps T027 `done`: the
  property the check was meant to prove (the page calls only GET /builds, /artifacts and /releases on the same origin) was
  verified by the reviewer twice, by code and by a runtime request log in headless Chrome. #173 is the follow-up to fix
  the acceptance command itself.
- #152 `check_shared_copy.py`: use argparse. #149 guard the `env -u SHIPYARD_SLOT` acceptance. #150 T025 octet-stream
  request body and 413 ordering (inferred: T025 uses the dependency approach; the lead to check). #157 `differences()`
  enum and const. #159 pin the hand-written `ErrorEnvelope` to `errors.yml`. #147 `environment.md` error-envelope row.
  #146 mark the Q-11 retry numbers as the default (assumed), not a user decision.

### Closed by the lead

- #132 wave 2 runner upload timeout: 10 s, recorded in the T024 hand-off.
- #136 wave 2 scaffold notes from the T019 review: `start-stack.sh` stops the slot's stack and refuses to wipe while a
  port is taken; the error mapping is in T020, T021 and T022.
- #148 stop and start scripts accept a dead pid file: verified in the T021 review.
- #131 `needs-decision`, a failed build can still leave a stored artifact: Nir chose option (a), recorded as Q-37.
- #154 the CI `stack` job syncs the four service venvs before `start-stack.sh`: done in T028 (PR #174).

### Deferred polish (by issue number)

#153 pip-audit dependencies pinned. #155 Starlette `TestClient` deprecation warning (`httpx2`). #158 conformance: examples
inside `anyOf`/`oneOf` branches. #160 `shared/errors.py` headers of another 4xx pass through to the 422. #165 artifact-store
hardening. #166 dashboard intake logging, `HEAD /`, id case, index. #172 release-service `BEGIN IMMEDIATE` reads, untested
`Settings.from_env`, unclosed executor in a test. #175 T028 contract checker gaps and a real no-retry check. #130 cosmetic
rewrap in `api-release-service.yml`.

## Proposed next wave (proposal only; the team stops at demo-ready and does not start it)

Inferred from the wave 3 outline in `docs/PLAN.md` § Waves: replace the HTTP event calls with a real queue (contracts keep
the payloads); auth between services (Q-09); retries, persistence and failure handling (#120, #131); e2e browser flows
(e2e-tester); possibly a React dashboard (user decision).

Suggested order, for the lead to decide: (1) the user answers the decision items above and Q-09 first, because the
queue and auth change the contracts and need the lead's contract change request; (2) a wave 3a spec task for the queue;
(3) auth and retries after it; (4) e2e flows last, as in wave 2 (tester last). No agents are launched by this report.

## Decisions needed from the user

1. #163 request size caps: (a) add to the contracts now, or (b) wave 3.
2. #170 dashboard version above 2^63-1: (a) store safely, no contract change; (b) contract caps versions at 2^63-1; (c) keep as a limitation.
3. #167 unexpected runner failure: (a) new state in the contract; (b) fail in code, no state change.
4. #171 event senders blocked by a hanging dashboard: (a) async client with drop after deadline; (b) accept for wave 2.
5. Wave 3 scope: queue, auth (Q-09), retries (#131), React dashboard or not. Already outlined in `docs/PLAN.md`; confirm before the wave starts.
