# Open questions

Every conflict or unclear point found while planning Shipyard. Nothing here is silently decided: each entry names
its sources, the options, and a status.

**Statuses:** `open` (known, not yet blocking; a default may be proposed), `needs-decision` (the user must choose;
becomes a `needs-decision` issue), `resolved-by-user-brief` (the user's brief settles it; the entry says where and
what follow-up remains). An entry marked **T012 default: assumed, pending user** means T012 writes that default
into the contracts, labelled "assumed, pending user" in the contract's `description`, until the user confirms or
changes it.

"User brief" below means the user's Shipyard brief for wave 1 as relayed by the lead in the T010 task prompt
(issue #9). It is not yet stored as a file in the repo (see Q-07).

## Process and repo conflicts

### Q-01 Where the contracts live
- **Conflict:** `docs/team/environment.md` § "Proposed by the lead" puts contracts at
  `docs/contracts/<service>/API.md`, `docs/contracts/<service>/DATA_MODEL.md` and `docs/contracts/SHARED.md`, and
  § "Layout map" maps `docs/API.md`/`docs/DATA_MODEL.md` to them. The user brief puts them at `contracts/*.yml`
  (`events.yml`, `errors.yml`, `api-<service>.yml`).
- **Also affected:** `CLAUDE.md` § "Rules for every agent" names `docs/API.md` and `docs/DATA_MODEL.md` as the
  frozen contracts; for Shipyard that rule must cover `contracts/**`. The brief has no per-service data-model
  contract; environment.md's `DATA_MODEL.md` (owned by `db-engineer`) has no place in wave 1.
- **Options:** (a) follow the brief and update environment.md's proposal and layout map; (b) keep both.
- **Status:** `resolved-by-user-brief` (brief: wave 1 deliverables). The brief is newer and explicit. Follow-up
  for the lead: update `docs/team/environment.md` (devops owns it, T005) so the layout map points
  `docs/API.md` to `contracts/api-<service>.yml`, the shared contract to `contracts/events.yml` and
  `contracts/errors.yml`, says `contracts/**` is frozen like any contract, and says where per-service data models
  go in wave 2.

### Q-02 Dashboard frontend shape
- **Conflict:** `docs/team/environment.md` § "Open" lists "whether the dashboard is server-rendered or a separate
  frontend" as undecided, and § "Layout map" says the UI folder is decided in wave 0. The synced
  `.claude/agents/architect.md` (step 2) defaults to React + TypeScript + Vite in `web/`. The user brief: plain
  HTML pages + a little JavaScript, served by the dashboard, no build step, no React (React may be considered in
  wave 3).
- **Status:** `resolved-by-user-brief` for the shape; React + Vite defaults do not apply. Still `open`: the UI
  folder name and the backend-dev/frontend-dev split. Proposed for wave 2 planning: `services/dashboard/static/`
  owned by frontend-dev, served by the dashboard app owned by backend-dev. Follow-up: environment.md § "Open" and
  § "Layout map".

### Q-03 "Wave 0" decisions vs waves 1-3
- **Conflict:** `docs/team/environment.md` (§ "Proposed by the lead", § "Open", § "Commands", § "Worktrees, ports
  and databases") defers the database engine and migration tool, the local start command, the port base and slot
  numbering, `pyproject.toml` per service, and auth between services to "wave 0". The user brief has three waves,
  and wave 1 is contracts only.
- **Options:** (a) settle them in a setup task at the start of wave 2 (they are not needed for contracts);
  (b) treat wave 1 as "wave 0" and add a task now; (c) the user decides them directly.
- **Status:** `needs-decision`. Recommendation: (a), except inter-service auth, which affects the contracts (Q-09).

### Q-04 Issue labels
- **Conflict:** the user brief asks for issue labels `todo`, `deferred`, `needs-decision`. `docs/team/lead.md`
  § "Communication" ("Requests become issues") says `task`, `needs-decision`, `deferred`, and
  `.github/ISSUE_TEMPLATE/task.yml` applies the label `task`.
- **Options:** (a) use `todo` in this repo and change the issue template (a synced core file); (b) keep `task`
  and treat `todo` as the status, not a label; (c) apply both.
- **Status:** `needs-decision`.

### Q-05 Number of fix rounds
- **Conflict:** the user brief caps reviewer/architect fix rounds at two. `docs/team/lead.md` § "Workflow" step 5
  and § "Rules" say one fix round per review, then the lead decides.
- **Unclear:** whether "two" means two fix rounds per review (fix, re-verify, fix, re-verify) or two in total for a
  task.
- **Options:** (a) the user's cap applies in Shipyard and is recorded as a local override; (b) change `lead.md` in
  the shared core.
- **Status:** `needs-decision` (where to record it, and the meaning of "two"). Until then the user's instruction
  outranks the synced process file.

### Q-06 Required aggregate check
- **Facts:** `main` has no branch protection (`gh api repos/regevha/shipyard/branches/main/protection` returns
  404 "Branch not protected", checked 2026-11-25), so no check is required today. A job can `needs:` only jobs in
  the same workflow, so a `ci-ok` job in a new `.github/workflows/ci.yml` (T011) cannot depend on the jobs in
  `.github/workflows/team-checks.yml`, which is synced from the shared core (listed in `docs/team/SYNC_FILES`) and
  runs on `pull_request` only.
- **Options:** (a) `ci-ok` aggregates `ci.yml` only, and branch protection requires `ci-ok` plus each
  team-checks job by name; (b) the shared core makes team-checks a reusable workflow (`workflow_call`) that
  `ci.yml` calls, so `ci-ok` covers it; (c) `ci-ok` polls the check-runs API for the head commit (fragile).
- **Status:** `needs-decision`. Turning on branch protection is a repo admin action for the user. T011 builds
  option (a)'s `ci-ok` either way.

### Q-07 The brief is not in the repo
- **Point:** there is no `docs/PRODUCT.md`, and the user's brief exists only in the lead's prompt and issue #9.
  Reviewers cannot check the contracts against it line by line.
- **Options:** store the brief verbatim (e.g. `docs/BRIEF.md`, lead-made) or quote it in issue #9.
- **Status:** `open` (lead follow-up).

### Q-08 Task table columns
- **Point:** the brief fixes the `docs/PLAN.md` task table columns (ID, task, acceptance command, files touched,
  status); `.claude/agents/architect.md` step 5b also lists owner and depends-on.
- **Status:** `resolved-by-user-brief`: the table has the brief's columns; owner and depends-on live in each
  `docs/tasks/Tnn.yml`, linked from the table.

## Ambiguities the contracts must settle (for T012)

### Q-09 Authentication between services
- **Point:** the brief says nothing about auth; `docs/team/environment.md` § "Open" lists it as undecided. Without
  it, anyone who can reach the dashboard's events endpoint can post fake events, and anyone who can reach
  release-service can approve.
- **Options:** (a) none in waves 1-2 (trusted local network), added in wave 3; (b) a shared bearer token per
  service; (c) mTLS.
- **Status:** `needs-decision`. T012 default, **assumed, pending user**: (a), with no security scheme in the
  OpenAPI files and a note in each `info.description`.

### Q-10 Who approves, and how "who" is known
- **Point:** release-service records "who and when". Without auth (Q-09), "who" is whatever the caller sends.
  Also unclear: may the requester approve their own release; can a decision be changed; can a rejected release be
  re-requested.
- **Status:** `needs-decision`. T012 default, **assumed, pending user**: the decision body carries `decided_by`
  (free string) and the server sets `decided_at`; one decision per release, final (a second decision is 409);
  a rejected release stays rejected, and a new release request is made instead; no self-approval rule.

### Q-11 Event delivery semantics
- **Point:** the brief says the three services POST events to the dashboard, but not: whether a sender waits,
  what happens if the dashboard is down (does a build fail?), retries, duplicates, or ordering.
- **Status:** `open`. T012 default, **assumed, pending user**: the dashboard answers 202 on accept; senders retry
  on network errors and 5xx with backoff, and a delivery failure never changes a build, upload or release
  outcome; every event has a unique `event_id` and the dashboard ignores repeats (idempotent, still 202);
  events may arrive out of order and the dashboard orders by `occurred_at`. These choices also suit the later queue.

### Q-12 Event envelope and versioning
- **Point:** the brief lists event kinds, not a common shape.
- **Status:** `open`. T012 default, **assumed, pending user**: envelope `{event_id, type, schema_version,
  occurred_at, source, data}`, `source` being a service name, `schema_version` an integer starting at 1.

### Q-13 One event or two for each outcome
- **Point:** the brief lists "build finished (passed or failed)" and "release approved or rejected" as single
  items. They could be one event with an outcome field or two event types each.
- **Status:** `open`. T012 default, **assumed, pending user**: one event each (`build.finished` with
  `outcome: passed | failed`, `release.decided` with `decision: approved | rejected`).

### Q-14 Events not in the brief's list
- **Point:** the runner "reports each step", release-service "blocks promotion", and the dashboard shows
  "failures", but the brief's event list has no step event, no promotion event and no upload-failure event.
- **Status:** `needs-decision`. T012 default, **assumed, pending user**: only the brief's five kinds; step
  results go in `build.finished.data.steps` (with the failing step, if any) and in the runner's own API; no
  promotion event.

### Q-15 IDs, timestamps and pagination
- **Status:** `open`. T012 default, **assumed, pending user**: IDs are UUID strings (`format: uuid`) assigned by
  the owning service; timestamps RFC 3339 in UTC with `Z` (`format: date-time`); list endpoints take `limit`
  (default 50, max 200) and `offset`, newest first.

### Q-16 What "blocks promotion" means and who calls promote
- **Point:** there is no deploy target and no fifth service. Unclear: what promotion does (a state change only,
  or a call to some deploy step), who calls it (a person through the dashboard, the runner, an external tool), and
  what a release points at (a build, an artifact version, or both).
- **Status:** `needs-decision`. T012 default, **assumed, pending user**: release-service has
  `POST /releases/{id}/promote`; it returns 409 unless the release is approved and records `promoted_at`;
  promotion is a recorded state change only; a release references one artifact (name + version); the caller is
  any client, including the dashboard UI; release-service does not call artifact-store to check the artifact
  exists.

### Q-17 Artifact version and checksum
- **Point:** "stores them with a version and checksum": who assigns the version (the runner, from the build, or
  the store, per artifact name), its format (integer, semver, build ID), the checksum algorithm, and what a
  re-upload of the same name and version does.
- **Status:** `needs-decision`. T012 default, **assumed, pending user**: the store assigns an integer version per
  artifact name, starting at 1; SHA-256 hex computed by the store; the uploader may send the expected checksum and
  a mismatch is 422; the upload records the `build_id` it came from.

### Q-18 Artifact upload format and limits
- **Status:** `open`. T012 default, **assumed, pending user**: raw body (`application/octet-stream`), artifact
  name in the path, `build_id` as a query parameter; max 100 MiB, else 413; download returns the bytes with the
  checksum in a response header. Storage backend: wave 2.

### Q-19 Pipeline definition format and execution
- **Point:** "runs a pipeline definition step by step": the definition format is not given, and running real
  shell commands on the runner host is a security decision.
- **Options:** (a) steps are shell commands executed on the runner host; (b) steps are simulated (each step
  declares an outcome or duration) until wave 3; (c) a restricted command list.
- **Status:** `needs-decision`. T012 default, **assumed, pending user** for the shape only: JSON body
  `{name, steps: [{name, command}]}`; execution semantics left to the user's decision before wave 2.

### Q-20 Run lifecycle
- **Status:** `open`. T012 default, **assumed, pending user**: `POST /runs` returns 202 with the run ID and runs
  in the background; `GET /runs/{id}` gives the status and per-step results; steps run in order and the run stops
  at the first failed step; no cancel and no re-run in wave 1-2; the runner uploads artifacts after a passed run.
  Which files a step produces as artifacts depends on Q-19.

### Q-21 Error envelope vs FastAPI defaults
- **Point:** the brief asks for one shared error envelope. FastAPI's built-in errors use `{"detail": ...}` and its
  generated OpenAPI adds `HTTPValidationError` for 422. Wave 2 must replace the default exception handlers and
  OpenAPI error responses, or the services will not match the contract.
- **Status:** `open`. T012 defines the envelope; the wave 2 setup task must include the override.

### Q-22 How wave 2 "diffs" FastAPI's OpenAPI against the contracts
- **Point:** FastAPI emits OpenAPI 3.1 with its own schema names and inline schemas, and it cannot emit
  cross-file `$ref`s such as `errors.yml#/$defs/ErrorEnvelope`. A literal text diff will never match.
- **Status:** `open` (wave 2). Needs a semantic comparison (paths, methods, status codes, resolved body schemas).

### Q-23 Dashboard read API
- **Point:** the frontend's JavaScript must fetch data from somewhere: the dashboard's own JSON endpoints (built
  from received events) or the other services directly.
- **Status:** `open`. T012 default, **assumed, pending user**: only the dashboard's own JSON endpoints; the
  dashboard never calls the other services.
