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
- **Status:** `answered-by-user` (2026-11-26, issue #25): option (a). The wave 2 setup task (T019) proposes these
  choices in `docs/team/environment.md`; no service task starts until the user approves the proposal. The database
  is SQLite for every service for now, with data access kept easy to swap (item 1 below). Item 2 below, that the
  lead decides ports, start commands, script names and per-service setup, was replaced later the same day by the
  setup-task decision quoted last: the setup task proposes them and the user approves. Inter-service auth stays as
  decided in Q-09.
- **User decisions (2026-11-26, #25):**

  > 1. Database (#25, wave 0 decisions): Use SQLite for every service for now. We plan to switch to another database later, so keep data access easy to swap.

  > 2. Ports, start commands, script names, per-service setup (#25): You, the lead, decide these. Set them all in one place (for example docs/environment.md) before any service work starts, so no two services clash.

  Later decision, which replaces item 2:

  > #25 Q-03: a setup task at the start of wave 2 proposes DB/migrations, start command, ports, per-service pyproject; Nir approves.

### Q-04 Issue labels
- **Conflict:** the user brief: "Every request or finding in an agent report becomes a GitHub issue labelled
  todo, deferred or needs-decision." `docs/team/lead.md`
  § "Communication" ("Requests become issues") says `task`, `needs-decision`, `deferred`, and
  `.github/ISSUE_TEMPLATE/task.yml` applies the label `task`.
- **Options:** (a) use `todo` in this repo and change the issue template (a synced core file); (b) keep `task`
  and treat `todo` as the status, not a label; (c) apply both.
- **Status:** `answered-by-user` (2026-11-26, issue #26): option (b). The label stays `task`; the two open issues
  labelled `todo` (#36, #112) were relabelled `task` on 2026-11-26. Closed issues keep their old labels.
- **User decision (2026-11-26, #26):**

  > #26 Q-04: keep "task" as the label; relabel the 2 "todo" issues.

### Q-05 Number of fix rounds
- **Brief (verbatim):** "Fix rounds are limited: if the reviewer and architect go around more than twice and the
  contracts still disagree, stop and report to me instead of looping." Earlier versions of this entry (and the
  lead's T010 prompt, and issue #27) said "caps fix rounds at two", which is the lead's paraphrase, not the brief.
- **Conflict:** `docs/team/lead.md` § "Workflow" step 5 and § "Rules" say one fix round per review, then the lead
  decides.
- **Unclear:** what counts as "going around" (one fix + re-review = one time?), whether the limit is per review or
  per task, and whether it covers only contract disagreements (the brief's wording) or every reviewer/architect
  loop (how the lead applied it to T010).
- **Former default (assumed until the user's answer below):** after two fix rounds on the same review with
  Blocking items still open, the lead stops and reports; applied to every reviewer/architect loop.
- **Options:** (a) the user's cap applies in Shipyard and is recorded as a local override; (b) change `lead.md` in
  the shared core.
- **Status:** `answered-by-user` (2026-11-26, issue #27): option (a), a Shipyard-only rule recorded in
  `docs/team/shipyard-overrides.md` (not synced; it overrides `docs/team/lead.md` § "Workflow" step 5 in this repo).
  The user's words do not limit it to contracts, so it applies to every review. Counting rounds per review is the
  lead's reading, not the user's words.
- **User decision (2026-11-26, #27):**

  > #27 Q-05: after 2 fix rounds with Blocking items still open, stop and report (Shipyard-only rule).

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
- **Status:** `answered-by-user` (2026-11-26, issue #28): option (a). The user added `ci-ok` to ruleset `Main1`
  himself. The lead checked it on 2026-11-26: `Main1` is active and requires the four team-checks jobs and `ci-ok`
  (GitHub Actions), with branches up to date; `GET repos/regevha/shipyard/rules/branches/main` lists `ci-ok`; `ci-ok`
  passed on main 71643fc. Issue #28 is closed.
- **User decision (2026-11-26, #28):**

  > 3. ci-ok as a required check (#28): I will add ci-ok to the Main1 ruleset myself in the GitHub settings. Do not change repo settings. After I tell you it's done, confirm that ci-ok shows as required.

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
- **Status:** `answered-by-user` (2026-11-26, issue #35): option (a). The change is made in the shared core and
  reaches this repo through a `team-sync-` PR; until then `docs/tasks/README.md` here still has the old lines 15 and
  30. Issue #35 stays open until that sync merges. CI checks neither field, so nothing is blocked.
- **User decision (2026-11-26, #35):**

  > #35 Q-24: shared-core docs/tasks/README.md adds architect as an owner and allows command strings as acceptance.

### Q-25 Is CI part of wave 1?
- **Brief (verbatim):** "Wave 1 is CONTRACTS ONLY. Write no service code." and, separately, "Set up CI from day
  one: a required aggregate check, a parse check that every contract and task spec is valid YAML, and a check that
  every example in the contracts validates against its schema." The wave 1 deliverables list does not name CI.
- **Point:** `docs/PLAN.md` calls wave 1 "contracts + CI" and plans T011 (CI) inside it. That placement is the
  lead's reading of "from day one", not a sentence of the brief.
- **Status:** `answered-by-user` (2026-11-26, issue #40): the former default. CI belongs in wave 1 (T011).
- **User decision (2026-11-26, #40):**

  > #40 Q-25: confirmed, CI belongs in wave 1.

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
- **Status:** `answered-by-user` (2026-11-26, issue #41): the outline in `docs/PLAN.md` § "Waves" stands, with
  wave 2 narrowed to the thinnest slice through all four services. Wave 3 scope refined by the project owner on
  2026-11-27 (issue #177): see Q-43 (the React dashboard moves to a later wave).
- **User decision (2026-11-26, #41):**

  > #41 Q-27: confirmed, wave 2 = thinnest slice through all four services; wave 3 = queue, auth, retries, persistence, e2e.

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
  removed from the contracts. Whether the dashboard pages may call it from the browser was open until the user's Q-32 answer (#89, no dashboard buttons in wave 2).
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
  contracts. How a faked step comes out failed was settled later by the user's Q-33 answer (#107).
- **User decision (2026-11-25, #34):**

  > #34 (Q-19) Pipeline steps: simulated until wave 3 (no real shell commands). Shape stays {name, steps:[{name, command}]}; the runner fakes each step's result.

### Q-20 Run lifecycle
- **Status:** `open`. T012 default, **assumed, pending user**: `POST /runs` returns 202 with the run ID and runs
  in the background; `GET /runs/{id}` gives the status and per-step results; steps run in order and the run stops
  at the first failed step; no cancel and no re-run in wave 1-2. The default's last part, that the runner uploads
  artifacts after a passed run, is superseded by the user's answers on Q-34 (#110: one fake artifact per build
  whose steps all passed) and Q-36 (#120: the upload runs before the build is marked passed, and a failed upload
  fails the build).

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
- **Status:** `resolved` by T017 (PR #123), following the user's Q-32 decision (#89): the frontend fetches
  only the dashboard's own JSON endpoints and the dashboard calls no other service. The user did not answer Q-23 in
  his own words; the lead read the #89 decision (no dashboard buttons, decide and promote go straight to
  release-service) as settling it, and T017 removed `x-assumed: [Q-23]`. Revisit in wave 3.

### Q-28 Run or build: one name for one concept
- **Point (found by T012):** the brief speaks of builds (build started, build finished) and the runner's job as
  running a pipeline definition. Q-17 (answered by the user, #33) and the Q-18 default call the identifier `build_id`; the Q-20 default calls
  the resource a run (`POST /runs`, `GET /runs/{id}`, the run ID). Two names for one concept would break the
  cross-service consistency the reviewer checks.
- **Options:** (a) one run is one build: the identifier is `build_id` in every file and the runner's paths stay
  `/runs` (`GET /runs/{build_id}`); (b) rename the runner's resource to `/builds`; (c) call it `run_id`
  everywhere and rename the events' fields.
- **Status:** `answered-by-user` (2026-11-26, issue #85): option (a), the former T012 default. T017 (PR #123) removed
  `x-assumed: [Q-28]` from `events.yml#/$defs/BuildId` and the runner's `Run` schema.
- **User decision (2026-11-26, #85):**

  > #85 Q-28: one run = one build; build_id everywhere; runner paths stay /runs/{build_id}.

### Q-29 Allowed characters in an artifact name
- **Point (found by T012):** the Q-18 default puts the artifact name in the URL path (`/artifacts/{name}`). Nothing
  says which characters a name may have (a slash, spaces, a length limit), or whether names are case-sensitive.
- **Status:** `answered-by-user` (2026-11-26, issue #86). T017 (PR #123) gives `events.yml#/$defs/ArtifactName`
  and the store's `{name}` parameter the pattern `^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$` with a guard against a
  trailing newline. This also closes the gap below (#103): `/` is rejected. Pipeline names follow the same rule
  (Q-35).
- **User decision (2026-11-26, #86):**

  > #86 Q-29: artifact names: letters, digits, . - _; starts with a letter or digit; 1-100 chars; case-sensitive; no / or spaces.
- **Former gap (review of T012, issue #103), closed by the answer above:** `ArtifactName` accepted `/`, which
  cannot be the `{name}` path segment (a name like `a/b` would not route to `/artifacts/{name}`).

### Q-30 Who requested a release
- **Point (found by T012):** the brief asks release-service to record who and when for the decision, not for the
  request. The Q-10 default mentions no self-approval rule, which only matters if the requester is known.
- **Options:** (a) the request body carries a free-string `requested_by`, like `decided_by`; (b) not recorded.
- **Status:** `answered-by-user` (2026-11-26, issue #87): option (a). T017 (PR #123) adds a required free-string
  `requested_by` to `ReleaseRequest`, `Release` and `ReleaseRequestedData` (and a nullable one to the dashboard's
  `ReleaseView`) and removes `x-assumed: [Q-30]`.
- **User decision (2026-11-26, #87):**

  > #87 Q-30: record a free-string requested_by on the request; remove x-assumed [Q-30].

### Q-31 Promoting twice, and promotion on the dashboard
- **Point (found by T012):** the user's Q-16 decision (#32) returns 409 unless the release is approved and records
  `promoted_at`; it does not say what a second promote of an approved, already promoted release returns (200 and
  unchanged, 200 with a new time, or 409). This part was open until the user's answer below.
- **Settled by the user, consequence noted:** the user's Q-14 decision (#31) has no promotion event, so the
  dashboard cannot show whether a release was promoted, although the brief's blocking of promotion is the point
  of release-service. That follows from the decision and is not reopened here; showing promotions on the
  dashboard would need the user to revisit Q-14.
- **Status:** `answered-by-user` (2026-11-26, issue #88) for the second promote: 200 with the release unchanged,
  written into T017 (PR #123). Promotion stays off the dashboard (Q-14 not reopened).
- **User decision (2026-11-26, #88):**

  > #88 Q-31: second promote returns 200 unchanged; promoted_at keeps the first time.

### Q-32 Who calls decision and promote, and from where
- **Point (found by T012):** the user's Q-16 decision (#32) says any client may call promote (decided). The Q-23
  default (then still assumed; now resolved by T017) says the frontend fetches only the dashboard's own endpoints
  and the dashboard never calls the other services. The clash below was open until the user's answer. If people approve, reject or promote from the dashboard pages, the browser either calls
  release-service directly (needs CORS, and the pages need release-service's address) or the dashboard forwards
  the call (the dashboard then calls another service, against Q-23). Nothing says who calls the decision endpoint
  at all.
- **Status:** `answered-by-user` (2026-11-26, issue #89). Decide and promote are called by any client directly on
  release-service; the dashboard has no write endpoint besides `POST /events` (T017, PR #123). Revisit in wave 3.
- **User decision (2026-11-26, #89):**

  > #89 Q-32: no dashboard buttons in wave 2; decide/promote go straight to release-service.

### Q-33 How a simulated step comes out failed
- **Point (follows from the user's Q-19 decision, #34):** steps are simulated until wave 3, the shape stays
  `{name, steps: [{name, command}]}`, and the runner fakes each step's result. Not said: how a faked step comes out
  failed. Without a way to fail, `build.finished` with outcome failed and the dashboard's failures view can never
  occur in waves 1-2.
- **Options (the shape stays as the user set it):** (a) every step passes (failures untestable until wave 3);
  (b) a convention inside `command`, for example a command of exactly `fail` fails and anything else passes;
  (c) random with a fixed seed or rate (non-deterministic tests); (d) change the shape after all, for example an
  optional per-step `simulate: passed|failed` (contradicts the decision that the shape stays).
- **Status:** `answered-by-user` (2026-11-26, issue #107): option (b), string equality on `command`; written into
  T017 (PR #123).
- **User decision (2026-11-26, #107):**

  > #107 Q-33: a step whose command is exactly "fail" fails; anything else passes.

### Q-34 Which artifacts a simulated run uploads
- **Point (found by T012, fix round 2):** the Q-20 default left the artifacts a run produces to Q-19. The user's
  Q-19 answer (#34) makes steps simulated and keeps the shape `{name, steps:[{name, command}]}`, but does not say
  what, if anything, a simulated run uploads to artifact-store.
- **Options:** (a) nothing until wave 3; (b) one fake artifact per passed build, named after the pipeline; (c) the
  definition names its outputs (a shape change, against the user's decision); (d) a step `command` convention.
- **Status:** `answered-by-user` (2026-11-26, issue #110): option (b), written into T017 (PR #123) together with
  #112. When the upload runs and what a failed upload means: Q-36. Pipeline names that are not valid artifact
  names: Q-35.
- **User decision (2026-11-26, #110):**

  > 4. Artifacts from a simulated run (Q-34, #110): Option (b). Each passed build uploads one fake artifact to artifact-store, named after the pipeline. Failed builds upload nothing. Add this to the contract change requests for the wave 2 start, together with #112.

### Q-35 A valid pipeline name can be an invalid artifact name
- **Point (found by T017, issue #119):** Q-34 names the fake artifact after the pipeline, but `PipelineName` was any
  non-empty string, so a pipeline such as `my pipeline` or `a/b` could run and then fail the Q-29 artifact-name rule.
- **Options:** (a) pipeline names follow the artifact-name rule and a bad name is rejected when the run is created;
  (b) the runner converts the name to a valid artifact name; (c) skip the upload for such names.
- **Status:** `answered-by-user` (2026-11-26, issue #119): option (a), written into T017 (PR #123):
  `events.yml#/$defs/PipelineName` has the `ArtifactName` rule and `POST /runs` answers 422 for a bad name.
- **User decision (2026-11-26, #119):**

  > #119: Pipeline names use the same rule as artifact names (Q-29): letters, digits, . - _; starts with a letter or digit; 1-100 chars; case-sensitive. A bad name is rejected with 422 when the pipeline is created. No slugifying.

### Q-36 When the fake artifact is uploaded, and a failed upload
- **Point (found by T017, issue #120):** Q-34 does not say whether the upload happens before or after
  `build.finished`, or what a failed upload means for the build.
- **Status:** `answered-by-user` (2026-11-26, issue #120): the upload runs after the last step passes and before the
  build is marked passed (so before `build.finished`, the contract's reading); a failed upload fails the build with the reason
  `artifact upload failed`; no retries in wave 2. Written into T017 (PR #123). How the reason is carried is the
  contract's choice, not the user's: a required, nullable `failure_reason` in the runner's `Run`,
  `BuildFinishedData` and the dashboard's `BuildView`, whose only value is that text. The contracts read "fails" as
  one attempt where anything but a 201 counts, including a network error or a timeout. Follow-ups: issue #131
  (`needs-decision`: a timeout after the store saved the bytes leaves an artifact for a failed build) and issue
  #132 (the wave 2 runner task picks the timeout).
- **User decision (2026-11-26, #120):**

  > #120: The fake upload runs after the last step passes and before the build is marked passed. If the upload fails, the build is failed with reason "artifact upload failed". No retries in wave 2.

### Q-37 A failed build can still leave a stored artifact
- **Point (found by the architect in T017 round 2, commit 1267398, PR #123; issue #131, `needs-decision`):** per #120 a
  failed upload fails the build. If artifact-store saved the bytes and answered 201 but the runner timed out first,
  an artifact and an `artifact.uploaded` event exist for a build marked failed.
- **Options:** (a) accept it in wave 2 (the dashboard may show an artifact for a failed build), revisit with retries in
  wave 3; (b) the runner deletes the artifact (a new endpoint or a contract change); (c) the dashboard filters or hides
  artifacts of failed builds.
- **Status:** `answered-by-user` (2026-11-26, issue #131): option (a). T023, T024, T025, T027 and T028 carried
  `assumed (#131)`, which now stands as the decision. Retries and cleanup are wave 3.
- **User decision (Nir's reply to the lead session, 2026-11-26 21:41 Asia/Jerusalem, recorded by the lead on #131):**

  > a

### Q-38 Coverage threshold per service
- **Point:** the lead proposed `fail_under = 85` for each of the four services; T021 proposed the same in its hand-off
  (`docs/tasks/T021.md`). Config holds it in each service's `pyproject.toml` (`[tool.coverage.report]`).
- **Status:** `answered-by-user` (2026-11-26 21:28 Asia/Jerusalem, source: the lead session chat, not GitHub): the lead
  said it would treat 85 as the starting value unless the user wanted another number, and the user replied with the
  single word below. GitHub corroboration, both written by the lead session: the lead's comment on PR #151 (T021, 2026-11-26
  19:57:39Z) says `Coverage fail_under = 85 confirmed by Nir.`, and the PR #151 description says `fail_under = 85 in all four
  (lead confirms)` (it does not mention Nir).
- **User decision (2026-11-26 21:28 Asia/Jerusalem, lead session chat):**

  > ok

### Q-39 Request size caps on the runner, release-service and `POST /events`
- **Point (issue #163, from T023; also T024 review #167):** the contracts set no request body cap and no 413 for
  `POST /runs`, `POST /releases` and the dashboard's `POST /events`; only artifact-store caps uploads (100 MiB). A
  3000-step, 3 MB definition was accepted in the T024 review.
- **Options (wave 2 summary):** (a) add caps to the contracts now; (b) leave them for wave 3.
- **Status:** `answered-by-user` (2026-11-27, issue #163): option (b). No contract change now; request size limits
  are part of the wave 3 scope (Q-43). #163 stays open for wave 3.
- **User decision (the project owner, 2026-11-27 08:42 Asia/Jerusalem, written in the wave 2 summary doc and confirmed in the lead
  session; recorded by the lead on #163):**

  > #163: (b), leave for wave 3. The services have no login yet, and wave 3 adds it, so add size limits then.

### Q-40 Artifact versions above 2^63-1
- **Point (issue #170, found by T026):** `events.yml` set no maximum on `ArtifactVersion`, so a version above 2^63-1
  was contract-valid, but the dashboard answered 500 for it (SQLite INTEGER overflow), release-service stored it as
  text and artifact-store answered 404 for such a download.
- **Options (wave 2 summary):** (a) the dashboard stores such versions safely, no contract change; (b) the contract
  caps the version at 2^63-1, so larger ones are rejected; (c) keep it as a limitation.
- **Status:** `answered-by-user` (2026-11-27, issue #170): option (b). Applied in T029:
  `events.yml#/$defs/ArtifactVersion` has `maximum: 9223372036854775807`; every version in the six files refers to
  it (`Artifact`, `ArtifactRef`, artifact-store's `{version}` path parameter, release-service's request body and
  `Release`, the dashboard's views). A larger value is 422 `validation_failed` wherever a version is received;
  artifact-store never assigns one. The code follows in T030-T032 (`docs/PLAN.md` § Waves).
- **User decision (the project owner, 2026-11-27 08:42 Asia/Jerusalem, written in the wave 2 summary doc and confirmed in the lead
  session; recorded by the lead on #170):**

  > #170: (b), cap versions in the contract. It is a one-line limit that makes the edge case explicit instead of a silent 500.

### Q-41 An unexpected error in a run's background task
- **Point (issue #167, T024 review):** an error nothing anticipated in the runner's background task was logged and
  the run stayed `running` for ever. `Run` and `BuildFinishedData` had no valid failed state for it: a failed build
  needs a `failed_step` or a `failure_reason`, and `FailureReason` was a closed enum whose only value was
  `artifact upload failed`.
- **Options (wave 2 summary):** (a) a new state in the contract; (b) fail the run in code, no new state.
- **Status:** `answered-by-user` (2026-11-27, issue #167): option (b). The condition in the decision is met (the
  failed state could not carry a reason for this case), so T029 changed the contract as little as possible:
  `FailureReason` gets a second value, `internal error` (the contract's name, after the `internal_error` error code;
  it names the runner as the cause and carries no exception text), and the state tables of `BuildFinishedData`,
  `Run` and `BuildView` get one row: outcome failed, `failed_step` null, `failure_reason` `internal error`, `steps`
  as the new `events.yml#/$defs/InterruptedRunSteps` (each step passed, failed or skipped, at most one failed: the
  step that was running when the error happened). No new run status. The upload row now requires exactly
  `artifact upload failed`. The code follows in T033 (runner) and T030 (dashboard intake accepts the new row).
- **User decision (the project owner, 2026-11-27 08:42 Asia/Jerusalem, written in the wave 2 summary doc and confirmed in the lead
  session; recorded by the lead on #167):**

  > #167: (b), mark it failed in code. A crash is a failure, and a stuck "running" build is a real bug. Change the contract only if the failed state cannot carry a reason.

- **Follow-up: the write that marks the run failed fails too (T029 open question 2, reviewer B1 on T029).** T033
  writes the failed state in a fresh session and retries it up to 3 times; the question was what happens if all
  three fail (for example the database is gone). Options: accept the rare case and name it in the contract; keep
  retrying in the background with a limit; or a startup or read-time check that fails runs stuck `running`.
  **Answered by the project owner (2026-11-27, Asia/Jerusalem, in the lead session, through the lead's
  multiple-choice question):**

  > Accept the rare case

  **Then superseded by the project owner (2026-11-27 09:44 Asia/Jerusalem, in the lead session):**

  > Rare cases should be ignored until end of wave 3

  So the case is ignored until the end of wave 3. Applied in T029: `api-pipeline-runner.yml` (the Unexpected
  errors paragraph of its info) and `events.yml#/$defs/InterruptedRunSteps` state the behaviour (an unexpected
  error during a run marks it failed with `internal error` and sends build.finished) with no absolute promise
  that a run is never left `running` and no clause for this case. T033 has no retry, test or hand-off note for it.

### Q-42 Event senders blocked by a hanging dashboard
- **Point (issue #171, T026 review):** pipeline-runner, artifact-store and release-service send events with a
  synchronous client from background tasks on the handler thread pool. A dashboard that accepts connections and
  never answers holds a thread about 7.5 s per event; 80 concurrent creates then one GET took 6.09 s, against the
  `docs/PLAN.md` convention that a slow dashboard never delays a response.
- **Options (wave 2 summary):** (a) send events with an async client and drop after a deadline; (b) accept it for
  wave 2.
- **Status:** `answered-by-user` (2026-11-27, issue #171): option (a), fixed now. Reading (the lead's, kept by the
  architect): the dashboard itself makes no outbound calls (it calls no other service), so the decision's
  outbound calls are the three senders' calls to the dashboard's `POST /events`. No contract change. The event
  sender convention in `docs/PLAN.md` § Conventions now has a total deadline of 5 s per event and an async sender
  off the handler thread pool; the code follows in T031-T033.
- **User decision (the project owner, 2026-11-27 08:42 Asia/Jerusalem, written in the wave 2 summary doc and confirmed in the lead
  session; recorded by the lead on #171):**

  > #171: (a), fix now. A deadline on the dashboard's outbound calls is a small change, and it still helps after the queue arrives.

- **Follow-up: the runner's simulated steps and its upload (T029 open question 1).** These still run on the
  request-handler thread pool (the `time.sleep` of each simulated step, and the upload to artifact-store with up
  to 10 s per httpx phase, #132), so under load they can delay unrelated requests to the runner. The decision
  above covers only the calls to the dashboard. Options: fix it in the wave 2 follow-ups (a new task after T033),
  or leave it to wave 3, where the queue and real steps change this code anyway. **Answered by the project owner
  (2026-11-27, Asia/Jerusalem, in the lead session, through the lead's multiple-choice question):**

  > Wave 3, with the queue

  Applied in T029: written into the wave 3 outline of `docs/PLAN.md` § Waves; T033 leaves this code as it is, and
  T034's pipeline-runner stopped-dashboard test measures against a baseline taken with the dashboard running, so
  this delay cannot fail it.

### Q-43 Wave 3 scope
- **Point:** Q-27 outlined wave 3 as the queue, auth, retries, persistence and e2e flows, with a React dashboard
  possible; the wave 2 summary asked the project owner to confirm the scope before wave 3 starts.
- **Status:** `answered-by-user` (2026-11-27, issue #177): wave 3 is the queue, retries and persistence, then
  end-to-end tests, plus login, request size limits (#163, Q-39) and a second look at dashboard buttons (Q-32). The
  React dashboard moves to a later wave. Written into the wave 3 outline of `docs/PLAN.md` § Waves (outline only,
  no task specs yet). Still to settle when wave 3 is planned: what login covers (people using release-service and
  the dashboard, the services calling each other (Q-09), or both).
- **User decision (the project owner, 2026-11-27 08:42 Asia/Jerusalem, written in the wave 2 summary doc and confirmed in the lead
  session; recorded by the lead on new issue #177):**

  > Wave 3: the queue, retries and persistence, then end-to-end tests, plus login, request size limits (#163) and a second look at dashboard buttons (Q-32). Leave the React dashboard for a later wave so wave 3 stays focused.

- **Confirmation (the project owner, lead session, 2026-11-27, covering Q-39 to Q-43):**

  > Yes. They are all decisions
