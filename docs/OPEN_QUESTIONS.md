# Open questions

Every conflict or unclear point found while planning Shipyard. Nothing here is silently decided: each entry names
its sources, the options, and a status.

**Statuses:** `open` (known, not yet blocking; a default may be proposed), `needs-decision` (the user must choose;
becomes a `needs-decision` issue), `resolved-by-user-brief` (the user's brief settles it; the entry quotes the
sentence of `docs/BRIEF.md` that settles it, word for word, and says what follow-up remains; an entry that cannot
quote such a sentence is never `resolved-by-user-brief`), `resolved` (settled by a repo change the entry names),
`answered-by-user` (the user answered the question after the brief; the entry gives the date and the issue, and
quotes the user's words as a blockquote; contracts drop `x-assumed` for it).
An entry marked **T012 default: assumed, pending user** means T012 writes that default
into the contracts, marked with `x-assumed: [Q-nn]` on the element it affects (rule in `docs/PLAN.md`
§ "Marking assumed defaults"), until the user confirms or changes it. For `needs-decision` entries the default
is only a labelled placeholder so the contracts can be complete; it is never presented as decided.

"User brief" below means the user's first message to the lead session, stored verbatim in
[`docs/BRIEF.md`](BRIEF.md) (Q-07). The first version of this file (T010) was written from the lead's T010 prompt,
which restated the brief and added the lead's own choices; T013 checked every "brief" claim against the verbatim
text, quotes it where it holds, and labels the rest as assumptions (Q-05, Q-08, Q-24, Q-25, Q-26, Q-27).

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
- **Brief (verbatim):** "contracts/events.yml: build started, build finished (passed or failed), artifact
  uploaded, release requested, release approved or rejected." / "contracts/api-*.yml: one file per service with
  endpoints, request and response shapes." / "contracts/errors.yml: one shared error envelope and the status
  codes, agreed once." The `<service>` slugs in the file names (`pipeline-runner`, `artifact-store`,
  `release-service`, `dashboard`) come from `docs/team/environment.md` § "Decided by the user", not from the brief.
- **Status:** `resolved-by-user-brief` (quoted above). The brief is newer and explicit. Follow-up (issue #36)
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
- **Brief (verbatim):** "It also serves a small web frontend, so there is no fifth service. The frontend is plain
  HTML pages with a little JavaScript to refresh the data, with no build step and no React for now; a React app
  can be considered in wave 3 if the dashboard needs it."
- **Status:** `resolved-by-user-brief` for the shape (quoted above); React + Vite defaults do not apply. Still `open`: the UI
  folder name and the backend-dev/frontend-dev split. Proposed for wave 2 planning: `services/dashboard/static/`
  owned by frontend-dev, served by the dashboard app owned by backend-dev. Follow-up: environment.md § "Open" and
  § "Layout map".

### Q-03 "Wave 0" decisions vs waves 1-3
- **Conflict:** `docs/team/environment.md` (§ "Proposed by the lead", § "Open", § "Commands", § "Worktrees, ports
  and databases") defers the database engine and migration tool, the local start command, the port base and slot
  numbering, `pyproject.toml` per service, and auth between services to "wave 0". The user brief: "docs/PLAN.md
  with the three waves" and "Wave 1 is CONTRACTS ONLY. Write no service code." (Whether CI belongs to wave 1 is
  the lead's reading, not the brief's words: Q-25.)
- **Options:** (a) settle them in a setup task at the start of wave 2 (they are not needed for contracts);
  (b) treat wave 1 as "wave 0" and add a task now; (c) the user decides them directly.
- **Status:** `needs-decision`. Recommendation: (a), except inter-service auth, which affects the contracts (Q-09).

### Q-04 Issue labels
- **Conflict:** the user brief: "Every request or finding in an agent report becomes a GitHub issue labelled
  todo, deferred or needs-decision." `docs/team/lead.md`
  § "Communication" ("Requests become issues") says `task`, `needs-decision`, `deferred`, and
  `.github/ISSUE_TEMPLATE/task.yml` applies the label `task`.
- **Options:** (a) use `todo` in this repo and change the issue template (a synced core file); (b) keep `task`
  and treat `todo` as the status, not a label; (c) apply both.
- **Status:** `needs-decision`.

### Q-05 Number of fix rounds
- **Brief (verbatim):** "Fix rounds are limited: if the reviewer and architect go around more than twice and the
  contracts still disagree, stop and report to me instead of looping." Earlier versions of this entry (and the
  lead's T010 prompt, and issue #27) said "caps fix rounds at two", which is the lead's paraphrase, not the brief.
- **Conflict:** `docs/team/lead.md` § "Workflow" step 5 and § "Rules" say one fix round per review, then the lead
  decides.
- **Unclear:** what counts as "going around" (one fix + re-review = one time?), whether the limit is per review or
  per task, and whether it covers only contract disagreements (the brief's wording) or every reviewer/architect
  loop (how the lead applied it to T010).
- **Default, assumed, pending user:** after two fix rounds on the same review with Blocking items still open, the
  lead stops and reports; applied to every reviewer/architect loop, not only contracts.
- **Options:** (a) the user's cap applies in Shipyard and is recorded as a local override; (b) change `lead.md` in
  the shared core.
- **Status:** `needs-decision` (where to record it, and what "more than twice" counts). Until then the brief's
  sentence, read as in the default above (a reading that goes beyond "and the contracts still disagree"),
  outranks the synced process file.

### Q-06 Required aggregate check
- **Facts (corrected by T015):** `main` has no classic branch protection (that API returns 404), but it has an
  active repository ruleset, `Main1` (created 2026-11-25T20:26+02:00, read with `gh api
  repos/regevha/shipyard/rulesets/28098519`): no deletion, no force-push, changes through a PR (0 approvals; extra approval required for unattributed changes), and
  required status checks = the four team-checks jobs, with branches required to be up to date. `ci-ok` is not
  required. The first version of this entry (T010) said no check was required; that was wrong, because only the
  classic protection API was checked. A job can `needs:` only jobs in
  the same workflow, so a `ci-ok` job in a new `.github/workflows/ci.yml` (T011) cannot depend on the jobs in
  `.github/workflows/team-checks.yml`, which is synced from the shared core (listed in `docs/team/SYNC_FILES`) and
  runs on `pull_request` only.
- **Options:** (a) `ci-ok` aggregates `ci.yml` only, and the `Main1` ruleset adds `ci-ok` to the four
  team-checks jobs it already requires; (b) the shared core makes team-checks a reusable workflow (`workflow_call`) that
  `ci.yml` calls, so `ci-ok` covers it; (c) `ci-ok` polls the check-runs API for the head commit (fragile).
- **Status:** `needs-decision` (issue #28). Changing the ruleset is a repo admin action for the user. T011 built
  `ci-ok` (merged in PR #51); it is green on main 50d9498 but not yet required.

### Q-07 The brief is not in the repo
- **Point:** there was no `docs/PRODUCT.md`, and the user's brief existed only in the lead session (the lead's
  T010 prompt was a restatement, not the text). Reviewers could not check the contracts against it line by line.
- **Status:** `resolved` by T013: the brief is stored verbatim in `docs/BRIEF.md`, with its source (the user's
  first message to the lead session, 2026-11-25 20:50 Asia/Jerusalem). The quote first posted on issue #9 left
  out the opening words and the process sections, and is superseded by `docs/BRIEF.md`.

### Q-08 Task table columns
- **Brief (verbatim):** "docs/PLAN.md with the three waves and a task table (ID, task, acceptance criterion that
  can actually be run, files touched, status)." `.claude/agents/architect.md` step 5b also lists owner and
  depends-on.
- **Status:** `resolved-by-user-brief` for the five columns (quoted above); owner and depends-on live in each
  `docs/tasks/Tnn.yml`, linked from the table.
- **Not in the brief:** that "acceptance criterion that can actually be run" means a shell command string. That is
  the lead's reading. `open`; default, **assumed, pending user**: each criterion is a command with its expected
  result, or is labelled as a non-command gate (e.g. a review verdict). Issue #47 (deferred).

### Q-24 Task spec format vs `docs/tasks/README.md`
- **Conflict:** `docs/tasks/README.md` (synced from the shared core, listed in `docs/team/SYNC_FILES`) line 15
  lists task owners as `db-engineer | backend-dev | frontend-dev | tester | e2e-tester | devops | chore`, with no
  `architect`; line 30 says `acceptance` holds `AC-nn` IDs from `docs/PRODUCT.md`. `docs/tasks/T010.yml` and
  `docs/tasks/T012.yml` have `owner: architect`, and T010-T012 list runnable command strings under `acceptance`,
  because Shipyard has no `docs/PRODUCT.md` and the user brief asks for an "acceptance criterion that can actually
  be run" (reading it as a command string is the lead's assumption, Q-08).
- **Options:** (a) change `README.md` in the shared core (add `architect` for spec and contract tasks; allow
  command strings when there is no `PRODUCT.md`); (b) a local note in a Shipyard-only file (e.g.
  `docs/team/environment.md`) that overrides those two lines; (c) a per-repo exception list read by CI, like
  `docs/team/branch_exemptions`.
- **Status:** `needs-decision`. CI does not check either field today (`scripts/ci/check_task_scope.py` reads only
  `files_touched`), so nothing is blocked yet.

### Q-25 Is CI part of wave 1?
- **Brief (verbatim):** "Wave 1 is CONTRACTS ONLY. Write no service code." and, separately, "Set up CI from day
  one: a required aggregate check, a parse check that every contract and task spec is valid YAML, and a check that
  every example in the contracts validates against its schema." The wave 1 deliverables list does not name CI.
- **Point:** `docs/PLAN.md` calls wave 1 "contracts + CI" and plans T011 (CI) inside it. That placement is the
  lead's reading of "from day one", not a sentence of the brief.
- **Status:** `needs-decision` (what the user meant). Default, **assumed, pending user**: CI is built in wave 1
  (T011), because day one is wave 1.

### Q-26 Contract file formats and the checker rules
- **Point:** the brief says what each contract file contains, not its format. OpenAPI 3.1.0 for `api-*.yml`,
  JSON Schema 2020-12 for `events.yml`/`errors.yml`, and every rule in `docs/PLAN.md` § "Contract file format"
  (examples rule, `x-assumed`, references, composition, the checker's libraries) are the lead's constraint and the
  architect's design, reviewed in T010, not the user's choice.
- **Options:** (a) keep them; (b) another format (e.g. plain YAML field lists, AsyncAPI for events).
- **Status:** `open`. Default, **assumed, pending user**: (a).

### Q-27 What waves 2 and 3 contain
- **Brief (verbatim), the only sentences about what later waves contain:** "A real event queue is a later wave." and "a React
  app can be considered in wave 3 if the dashboard needs it." Plus "Stop at the end of wave 1. ... Do not start
  wave 2."
- **Point:** `docs/PLAN.md` § "Waves" puts the services in wave 2 and the queue, auth, retries, persistence and
  e2e flows in wave 3. That split is the lead's outline, not the brief's.
- **Status:** `needs-decision` (what the user wants in each wave). Default, **assumed, pending user**: the outline
  in `docs/PLAN.md`, to be confirmed before wave 2 is planned in detail.

## Ambiguities the contracts must settle (for T012)

### Q-09 Authentication between services
- **Point:** the brief says nothing about auth; `docs/team/environment.md` § "Open" lists it as undecided. Without
  it, anyone who can reach the dashboard's events endpoint can post fake events, and anyone who can reach
  release-service can approve.
- **Options:** (a) none in waves 1-2 (trusted local network), added in wave 3; (b) a shared bearer token per
  service; (c) mTLS.
- **Status:** `answered-by-user` (2026-11-25, issue #29): option (a), the former T012 default. The OpenAPI files
  have no security scheme and say so in each `info.description`; `x-assumed: [Q-09]` is removed.
- **User decision (2026-11-25, #29):**

  > #29 (Q-09) Auth between services: none in waves 1-2 (trusted local network); revisit in wave 3.

### Q-10 Who approves, and how "who" is known
- **Point:** release-service records "who and when". Without auth (Q-09), "who" is whatever the caller sends.
  Also unclear: may the requester approve their own release; can a decision be changed; can a rejected release be
  re-requested.
- **Status:** `answered-by-user` (2026-11-25, issue #30): the former T012 default is kept. The decision body
  carries `decided_by` (free string) and the server sets `decided_at`; one decision per release, final (a second
  decision is 409); a rejected release stays rejected, and a new release request is made instead; no
  self-approval rule. `x-assumed: [Q-10]` is removed from the contracts.
- **User decision (2026-11-25, #30):**

  > #30 (Q-10) Approvals: keep the T012 default. decided_by is a free string, server sets decided_at, one final decision per release (a second is 409), rejected stays rejected (re-request = new release), no self-approval rule.

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
- **Status:** `answered-by-user` (2026-11-25, issue #31): the former T012 default. Only the brief's five kinds;
  step results go in `build.finished.data.steps` (with the failing step, if any) and in the runner's own API; no
  promotion event and no step events. `x-assumed: [Q-14]` is removed from the contracts.
- **User decision (2026-11-25, #31):**

  > #31 (Q-14) Events: only the five kinds in the brief. Step results inside build.finished.data.steps and the runner API; no promotion event, no step events.

### Q-15 IDs, timestamps and pagination
- **Status:** `open`. T012 default, **assumed, pending user**: IDs are UUID strings (`format: uuid`) assigned by
  the owning service; timestamps RFC 3339 in UTC with `Z` (`format: date-time`); list endpoints take `limit`
  (default 50, max 200) and `offset`, newest first.

### Q-16 What "blocks promotion" means and who calls promote
- **Point:** there is no deploy target and no fifth service. Unclear: what promotion does (a state change only,
  or a call to some deploy step), who calls it (a person through the dashboard, the runner, an external tool), and
  what a release points at (a build, an artifact version, or both).
- **Status:** `answered-by-user` (2026-11-25, issue #32): the former T012 default is kept. release-service has
  `POST /releases/{id}/promote`; it returns 409 unless the release is approved and records `promoted_at`;
  promotion is a recorded state change only; a release references one artifact (name + version); any client may
  call it; release-service does not call artifact-store to check the artifact exists. `x-assumed: [Q-16]` is
  removed from the contracts. Whether the dashboard pages may call it from the browser remains open (Q-32).
- **User decision (2026-11-25, #32):**

  > #32 (Q-16) Promotion: keep the T012 default. POST /releases/{id}/promote, 409 unless approved, records promoted_at, state change only; a release references one artifact (name + version); any client may call it; no existence check against artifact-store.

### Q-17 Artifact version and checksum
- **Point:** "stores them with a version and checksum": who assigns the version (the runner, from the build, or
  the store, per artifact name), its format (integer, semver, build ID), the checksum algorithm, and what a
  re-upload of the same name and version does.
- **Status:** `answered-by-user` (2026-11-25, issue #33): the former T012 default is kept. The store assigns an
  integer version per artifact name, starting at 1; SHA-256 hex computed by the store; the uploader may send the
  expected checksum and a mismatch is 422; the upload records the `build_id` it came from. `x-assumed: [Q-17]` is
  removed from the contracts.
- **User decision (2026-11-25, #33):**

  > #33 (Q-17) Artifacts: keep the T012 default. Store assigns an integer version per name from 1; SHA-256 hex computed by the store; optional expected checksum, mismatch 422; upload records build_id.

### Q-18 Artifact upload format and limits
- **Status:** `open`. T012 default, **assumed, pending user**: raw body (`application/octet-stream`), artifact
  name in the path, `build_id` as a query parameter; max 100 MiB, else 413; download returns the bytes with the
  checksum in a response header. Storage backend: wave 2.

### Q-19 Pipeline definition format and execution
- **Point:** "runs a pipeline definition step by step": the definition format is not given, and running real
  shell commands on the runner host is a security decision.
- **Options:** (a) steps are shell commands executed on the runner host; (b) steps are simulated (each step
  declares an outcome or duration) until wave 3; (c) a restricted command list.
- **Status:** `answered-by-user` (2026-11-25, issue #34): steps are simulated until wave 3, a variant of option
  (b) that keeps the shape `{name, steps: [{name, command}]}` (no per-step outcome field). The runner records
  each `command` and never executes it, and fakes each step's result. `x-assumed: [Q-19]` is removed from the
  contracts. How a faked step comes out failed is not decided: Q-33 (issue #107).
- **User decision (2026-11-25, #34):**

  > #34 (Q-19) Pipeline steps: simulated until wave 3 (no real shell commands). Shape stays {name, steps:[{name, command}]}; the runner fakes each step's result.

### Q-20 Run lifecycle
- **Status:** `open`. T012 default, **assumed, pending user**: `POST /runs` returns 202 with the run ID and runs
  in the background; `GET /runs/{id}` gives the status and per-step results; steps run in order and the run stops
  at the first failed step; no cancel and no re-run in wave 1-2; the runner uploads artifacts after a passed run.
  Which files a step produces as artifacts depended on Q-19; the user's Q-19 answer (#34: simulated steps) does
  not say, so it is now Q-34 (#110, needs-decision).

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

### Q-28 Run or build: one name for one concept
- **Point (found by T012):** the brief speaks of builds (build started, build finished) and the runner's job as
  running a pipeline definition. Q-17 (answered by the user, #33) and the Q-18 default call the identifier `build_id`; the Q-20 default calls
  the resource a run (`POST /runs`, `GET /runs/{id}`, the run ID). Two names for one concept would break the
  cross-service consistency the reviewer checks.
- **Options:** (a) one run is one build: the identifier is `build_id` in every file and the runner's paths stay
  `/runs` (`GET /runs/{build_id}`); (b) rename the runner's resource to `/builds`; (c) call it `run_id`
  everywhere and rename the events' fields.
- **Status:** `open`. T012 default, **assumed, pending user**: (a). Marked on `events.yml#/$defs/BuildId` and on
  the runner's `Run` schema.

### Q-29 Allowed characters in an artifact name
- **Point (found by T012):** the Q-18 default puts the artifact name in the URL path (`/artifacts/{name}`). Nothing
  says which characters a name may have (a slash, spaces, a length limit), or whether names are case-sensitive.
- **Status:** `open`, no default. The contracts only require a non-empty string (`events.yml#/$defs/ArtifactName`)
  and say the rule is not settled.
- **Known gap (review of T012, issue #103):** `ArtifactName` currently accepts `/`, which cannot be the
  `{name}` path segment (a name like `a/b` would not route to `/artifacts/{name}`). Not settled here: rejecting
  `/`, percent-encoding it, or another rule is part of this question.

### Q-30 Who requested a release
- **Point (found by T012):** the brief asks release-service to record who and when for the decision, not for the
  request. The Q-10 default mentions no self-approval rule, which only matters if the requester is known.
- **Options:** (a) the request body carries a free-string `requested_by`, like `decided_by`; (b) not recorded.
- **Status:** `needs-decision` (issue #87). T012 default, **assumed, pending user** (placeholder set by the lead,
  review issue #94): (b), the requester is not recorded. Marked with `x-assumed: [Q-30]` on
  `api-release-service.yml` `ReleaseRequest` and `Release` and on `events.yml#/$defs/ReleaseRequestedData`.
  Choosing (a) later is a contract change.

### Q-31 Promoting twice, and promotion on the dashboard
- **Point (found by T012):** the user's Q-16 decision (#32) returns 409 unless the release is approved and records
  `promoted_at`; it does not say what a second promote of an approved, already promoted release returns (200 and
  unchanged, 200 with a new time, or 409). This part is open.
- **Settled by the user, consequence noted:** the user's Q-14 decision (#31) has no promotion event, so the
  dashboard cannot show whether a release was promoted, although the brief's blocking of promotion is the point
  of release-service. That follows from the decision and is not reopened here; showing promotions on the
  dashboard would need the user to revisit Q-14.
- **Status:** `open`, no default. The contracts leave the second promote unspecified (said in the operation's
  description) and the dashboard's release view has no promotion field.

### Q-32 Who calls decision and promote, and from where
- **Point (found by T012):** the user's Q-16 decision (#32) says any client may call promote (decided). The Q-23
  default (still assumed, pending user) says the frontend fetches only the dashboard's own endpoints and the
  dashboard never calls the other services. The clash below remains open. If people approve, reject or promote from the dashboard pages, the browser either calls
  release-service directly (needs CORS, and the pages need release-service's address) or the dashboard forwards
  the call (the dashboard then calls another service, against Q-23). Nothing says who calls the decision endpoint
  at all.
- **Status:** `open`, no default. The contracts list the caller as any client and add no dashboard write
  endpoint; the who-calls-whom table in `contracts/api-dashboard.yml` points here.

### Q-33 How a simulated step comes out failed
- **Point (follows from the user's Q-19 decision, #34):** steps are simulated until wave 3, the shape stays
  `{name, steps: [{name, command}]}`, and the runner fakes each step's result. Not said: how a faked step comes out
  failed. Without a way to fail, `build.finished` with outcome failed and the dashboard's failures view can never
  occur in waves 1-2.
- **Options (the shape stays as the user set it):** (a) every step passes (failures untestable until wave 3);
  (b) a convention inside `command`, for example a command of exactly `fail` fails and anything else passes;
  (c) random with a fixed seed or rate (non-deterministic tests); (d) change the shape after all, for example an
  optional per-step `simulate: passed|failed` (contradicts the decision that the shape stays).
- **Status:** `needs-decision` (issue #107), no default. The contracts fix no mechanism; `contracts/api-pipeline-runner.yml`
  says this is open. Blocks wave 2 runner behaviour, not the wave 1 contract shape.

### Q-34 Which artifacts a simulated run uploads
- **Point (found by T012, fix round 2):** the Q-20 default left the artifacts a run produces to Q-19. The user's
  Q-19 answer (#34) makes steps simulated and keeps the shape `{name, steps:[{name, command}]}`, but does not say
  what, if anything, a simulated run uploads to artifact-store.
- **Options:** (a) nothing until wave 3; (b) one fake artifact per passed build, named after the pipeline; (c) the
  definition names its outputs (a shape change, against the user's decision); (d) a step `command` convention.
- **Status:** `needs-decision` (issue #110), no default. `contracts/api-pipeline-runner.yml` says it is not
  settled. Blocks the wave 2 runner-to-store upload.
