# Shipyard plan

Shipyard is a build and release platform made of four Python + FastAPI services that talk over plain HTTP:

| Service | Does |
| --- | --- |
| `pipeline-runner` | Runs a pipeline definition step by step; reports each step and the final result. |
| `artifact-store` | Accepts uploads from the runner, stores them with a version and a checksum, serves them back. |
| `release-service` | Holds a release request, records an approve or reject decision (who and when), blocks promotion until approved. |
| `dashboard` | Exposes an events endpoint the other three POST to; shows builds, artifacts, approvals and failures; serves a small web frontend (plain HTML + a little JavaScript, no build step, no React). |

There is no fifth service. A real event queue comes in a later wave. Unclear points and conflicts are tracked in
[`docs/OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md); none are silently decided here.

## Wave 1: goals and non-goals

**Goals**
- Agree every interface once, as machine-checkable files under `contracts/` (format below).
- `contracts/events.yml`: build started, build finished (passed or failed), artifact uploaded, release requested,
  release approved or rejected; each with fields, types and an example.
- `contracts/api-<service>.yml` for the four services: endpoints, request and response shapes.
- `contracts/errors.yml`: one shared error envelope and the status codes.
- `docs/OPEN_QUESTIONS.md`: every conflict or unclear point, with sources and options.
- CI (placed in wave 1 by the lead, Q-25): a required aggregate check (`ci-ok`), a YAML parse check of every contract and every `docs/tasks/*.yml`, and
  a check that every example in the contracts validates against its schema.

**Non-goals (wave 1)**
- No service code, no `services/` folder, no `pyproject.toml`, no database, no Docker.
- No decision on database engine, port base, start command or inter-service auth (see Q-03, Q-09).
- No event queue; no dashboard UI; no React.
- No changes to the synced team files (`CLAUDE.md`, `docs/team/lead.md`, `.claude/agents/`,
  `.github/workflows/team-checks.yml`); needed changes are listed as open questions.

## Waves

**Wave 1: contracts + CI (T010-T013).** (The brief says "Wave 1 is CONTRACTS ONLY"; putting CI in wave 1 is the lead's
reading of "Set up CI from day one", Q-25. The brief's text: [`docs/BRIEF.md`](BRIEF.md).) Order: T010 (this plan)
merges first, because `scripts/ci/check_task_scope.py` reads `docs/tasks/<ID>.yml` from the base branch; then T011
(CI); then T012 (contracts), which must pass T011's checker. T011 and T012 have disjoint `files_touched`, but T012
depends on T011, so they run one after the other.

**Wave 2: the thinnest slice through all four services, built against the contracts (Q-27, confirmed by the user on
2026-11-26).** The setup is the one in `docs/team/environment.md` § "Wave 2 setup (T019, approved)", approved by
Nir on #25 on 2026-11-26. SQLite for every service, data access behind `app/repos/` so it is easy to swap (user
decision on #25, quoted in Q-03); no migrations in wave 2. The contract changes of T020 (#121; #136 needs none)
are the last before the build: `contracts/**` is frozen from the start of T021 until the end of wave 2, except
for a Blocking defect through the lead. At most 3 build agents at a time; tasks of one sub-wave have disjoint
`files_touched` (checked in `docs/tasks/T020.yml`). Four sub-waves, each starting when the previous one is merged:

- **2a, foundation (one agent at a time): T021, then T022.** T021 (devops) scaffolds the four service projects
  and `stack-tests/` (pyproject, `uv.lock`, `.python-version`), the root `.gitignore` (#8), `scripts/dev/*.sh`
  (with the #136 stop-or-refuse fix), `scripts/ci/check_shared_copy.py` and the CI matrix. To keep CI green
  before any service logic exists, each service gets a minimal `app/main.py` (an empty FastAPI app) and
  `tests/test_main.py`, and the dashboard a placeholder `static/index.html`. T022 (backend-dev) then writes
  `shared/errors.py` and `shared/openapi_conformance.py` with their tests and copies all four files into every
  service. T022 runs after T021 because its copied tests run in the service projects T021 creates; it never
  touches `app/main.py`.
- **2b, three services (3 agents): T023 dashboard backend, T024 pipeline-runner, T025 artifact-store.** From
  here each service task owns its service's `app/main.py`, `tests/test_main.py`, `pyproject.toml` and
  `uv.lock`; the copies from T022 stay untouched. The dashboard goes first because the UI builds on it.
- **2c (2 agents): T026 release-service, T027 dashboard UI (frontend-dev, `services/dashboard/static/`).**
  release-service calls no service but the dashboard, so it can wait; T027 needs T023's read API for its browser
  smoke test against the real backend.
- **2d (1 agent): T028 (tester).** `stack-tests/` starts all four with `scripts/dev/start-stack.sh`, runs a
  pipeline, uploads, requests, approves, promotes and checks the dashboard read API; adds the CI `stack` job;
  writes `docs/DEMO.md`. It runs last because it tests every other task's code.

The user decisions each task must follow are written into its spec with their Q-numbers: Q-28 (`build_id`,
`/runs/{build_id}`), Q-29 and #119 (name rule, 422 for a bad pipeline name), Q-30 (`requested_by`), Q-31
(idempotent promote), Q-32 (no dashboard buttons), Q-33 (a command of exactly `fail` fails), Q-34 (one fake
artifact per passed build, named after the pipeline), Q-36 and #120 (upload after the last step, failure reason
`artifact upload failed`, no retries). #132: T024 picks the upload timeout (10 s) and records it in its hand-off. #131 was
decided by Nir on 2026-11-26: option (a), a failed build can show an artifact (Q-37). The specs marked it
`assumed (#131)`; that assumption now stands as the decision.

**Wave 3: hardening (outline only; confirmed by the user, Q-27).** Replace the HTTP event calls with a real queue (the
contracts keep the event
payloads); auth between services if not settled earlier; retries, persistence and failure handling; e2e browser
flows (e2e-tester); possibly a React dashboard (user decision at that point).

## Contract file format

T011 (checker) and T012 (contracts) follow this section exactly. The formats and rules below are the lead's constraint and the architect's design, not the user's brief (Q-26, assumed, pending user). "MUST" rules are enforced by
`scripts/ci/check_contracts.py`; anything not listed here is not checked.

### Files
- Exactly these names may exist under `contracts/` (no subfolders, no other files): `events.yml`, `errors.yml`,
  `api-pipeline-runner.yml`, `api-artifact-store.yml`, `api-release-service.yml`, `api-dashboard.yml`.
  Any other file under `contracts/` is an error. A missing file is not an error for the checker (T012's acceptance
  checks that all six exist).
- Every file is UTF-8 YAML with a single document whose root is a mapping. It is parsed with `yaml.safe_load`
  plus a loader that rejects duplicate mapping keys (an error, not a silent overwrite).
- Base URI: each file `<name>` has the base URI `https://shipyard.invalid/contracts/<name>`. In `events.yml` and
  `errors.yml` this MUST be written as the root `$id`. OpenAPI files have no `$id` at the root; the checker assigns
  them that URI.

### YAML must load as JSON (all six files)
Contracts are JSON data written in YAML. After loading, the checker walks every node and reports each violation as
a normal failure line (`<file>: <JSON pointer>: <message>`, no traceback); it runs before any other check of that
file, and a file with a violation gets no further checks.
- Every mapping key MUST be a string. Quote anything YAML would read otherwise: status codes (`"200":`, not
  `200:`), `"true"`, `"null"`, numbers.
- Every value MUST be a JSON type: `str`, `int`, `float`, `bool`, `None`, `list` or `dict`. Timestamps and dates
  MUST be quoted (`"2026-11-25T10:00:00Z"`, not a bare timestamp, which loads as `datetime`).
- YAML 1.1 surprises are the author's job: quote strings such as `on`, `off`, `yes`, `no` and version-like values
  such as `"0.1"` or `"1.10"` whenever a string is meant (the loader gives `bool`/`float` and the schema check then
  fails, which is correct but confusing).
- Non-finite floats (`.nan`, `.inf`, `-.inf`) and YAML-only types (`!!binary` bytes, `!!set`, timestamps and
  dates) are not JSON values: each is an error.
- YAML merge keys (`<<`) are rejected: the loader fails on any `<<` key with a message naming it (merge keys are
  not supported in contracts; write the keys out).
- The self-test has one failing fixture per case: an unquoted integer key, an unquoted timestamp value, an unquoted
  date value, an unquoted `on` where the schema says `type: string`, `.nan`, `.inf`, `!!binary`, `!!set` and a
  `<<` merge key.

### Marking assumed defaults
A contract element whose shape comes from a default in `docs/OPEN_QUESTIONS.md` ("T012 default: assumed, pending
user") MUST carry `x-assumed: [Q-nn, ...]` on the closest object it affects (a schema, a property schema, an
OpenAPI operation, parameter or response). It is the only marker; a description line alone does not count. The
checker fails if an `x-assumed` value is not a non-empty list of strings matching `^Q-\d{2}$`, or names an ID with
no `### Q-nn` heading in `docs/OPEN_QUESTIONS.md` (relative to `--root`). `x-assumed` is never put inside example
values. Assumed elements are never presented as decided, and `needs-decision` questions get only the labelled
default.

### `errors.yml` and `events.yml` (JSON Schema 2020-12)
- Root keys: `$schema: https://json-schema.org/draft/2020-12/schema` (MUST), `$id` (MUST, as above),
  `$defs` (MUST, non-empty mapping). The whole file MUST be a valid 2020-12 schema
  (`Draft202012Validator.check_schema`).
- Every entry directly under `$defs` MUST have `examples:`, a non-empty list. Each list item is one example of
  that schema.
- No cross-file `$ref`s: every `$ref` in these two files MUST start with `#`. Only `api-*.yml` files may refer to
  other files.
- `events.yml`: one `$defs` entry per event type (plus shared parts such as an envelope, which also carry
  `examples`). The root MUST have `oneOf`, a list of `$ref`s, one to each event type's `$defs` entry, so the root
  schema is "any valid event" (the body of the dashboard's events endpoint). "Event types" means exactly the
  `$defs` entries that are targets of the root `oneOf` `$ref`s; any other `$defs` entry (for example the envelope)
  is a shared part. Event names and the envelope are T012's content, not fixed here.
- Composition: an `allOf` member is a schema that appears inline in an `allOf` list or is the target of a `$ref`
  in one. The outermost composer (a schema with `allOf` that is not itself an `allOf` member) MUST have
  `unevaluatedProperties: false` and MUST NOT have `additionalProperties: false`. Every `allOf` member, including
  one that itself has `allOf`, MUST NOT have `additionalProperties: false` or `unevaluatedProperties: false`: it
  stays open. In 2020-12 `unevaluatedProperties` sees the properties evaluated through nested `allOf` and `$ref`,
  so the outermost close covers every level. The checker fails on each breach. This rule applies to
  the OpenAPI files' schemas too. Without it every example of a composed schema fails.
- `errors.yml`: MUST define `$defs/ErrorEnvelope` (the only error body any service returns) and `$defs/ErrorCode`
  (a schema with `enum` of the machine-readable error codes). The root MUST have `x-status-codes`: a list of
  mappings `{status: <int 400-599>, code: <string>, meaning: <string>}`; every `code` MUST appear in
  `$defs/ErrorCode/enum`, and every `(status, code)` pair MUST be unique.

### `api-<service>.yml` (OpenAPI 3.1.0)
- `openapi: 3.1.0` exactly; `info.title` MUST equal the service name from the file name; `info.version` is a
  string. No root `jsonSchemaDialect` (the OpenAPI 3.1 default dialect, based on 2020-12, applies). The document
  MUST pass `openapi-spec-validator` (OpenAPI 3.1 validation), run with `base_uri` set to the file's own
  `file://` URL so that cross-file `$ref`s resolve to the sibling files on disk, never over the network.
- Every entry under `components/schemas` MUST have `examples:`, a non-empty list (as above).
- Every media type object that has a `schema`, under `paths/.../requestBody/content`,
  `paths/.../responses/<status>/content`, `components/requestBodies/<Name>/content` or
  `components/responses/<Name>/content`, MUST have `examples:`, a non-empty mapping of Example Objects, each with a `value`. `externalValue` is not
  allowed. Responses without `content` (for example 204) need nothing.
- The singular `example` keyword is not allowed in Schema, Media Type, Parameter or Header objects, so there is
  one form only. This means the keyword; a property named `example` (a key under `properties`) or the key
  `example` inside an example value is not affected.
- Error responses: for every response whose status is `4XX`, `5XX` or a number from 400 to 599, the checker
  first follows the response's `$ref` (to `components/responses`, through any chain of `$ref`s; a target reached
  twice is a loop and an error). The final Response Object's `content` MUST have exactly one key,
  `application/json`, whose `schema` is exactly `{$ref: errors.yml#/$defs/ErrorEnvelope}` (no other keyword
  beside the `$ref`). Each numeric error status MUST appear as a `status` in `errors.yml#/x-status-codes`. Status keys are quoted
  strings (see "YAML must load as JSON").
- `default` responses are not allowed (list the statuses).

### References
- Only two forms are allowed. Inside a file: `#<pointer>`, e.g. `#/$defs/BuildStarted`,
  `#/components/schemas/Artifact`. Across files: `<file>#<pointer>` where `<file>` is exactly one of the six file
  names, e.g. `errors.yml#/$defs/ErrorEnvelope`. `<pointer>` is empty or an RFC 6901 pointer starting with `/`.
- Every other form is an error: an absolute URI (`https:`, `file:`, `urn:` and so on), `./` or `../` paths, a
  file without `#`, any other file name. The value MUST be a string, and the target MUST exist.
- Scanned everywhere: the checker checks every mapping key `$ref` at any depth of every contract file, including
  inside data keywords (`default`, `const`, `enum`, `examples`) and Example Object `value`s, because some
  validators follow them. So example data never contains a `$ref` key. OpenAPI `$ref`s outside schemas (to
  `components/responses`, `components/requestBodies`, `components/parameters`, `components/examples`) follow the
  same rules.
- Network: references are resolved only from the files on disk. jsonschema uses the preloaded
  `referencing.Registry` with no fetching retrieve function (an unknown URI is an error);
  `openapi-spec-validator` / `jsonschema-path` get file handlers only, no `http`/`https` handlers. The checker
  never opens a network connection. Its self-test runs with socket creation blocked (`socket.socket` and
  `socket.create_connection` patched to raise) and must still pass, and includes a fixture with an `https:`
  `$ref` that must fail as a reference-form error, not a network error.

### What "every example validates against its schema" means
The checker loads all contract files into one `referencing.Registry`, each as a 2020-12 resource under its base
URI. For each (schema location, example) pair it validates the example with
`Draft202012Validator({"$ref": "<base URI>#<JSON pointer to the schema>"}, registry=registry,
format_checker=Draft202012Validator.FORMAT_CHECKER)`. Format assertion is on: `jsonschema[format-nongpl]` is
installed, and before any check the checker exits 2 if `date-time`, `uuid` or `uri` is missing from
`Draft202012Validator.FORMAT_CHECKER.checkers`. The pairs are:

| File | Schema location (JSON pointer) | Examples |
| --- | --- | --- |
| `events.yml`, `errors.yml` | `/$defs/<Name>` | each item of `/$defs/<Name>/examples` (the envelope's examples are checked against the envelope only) |
| `events.yml` | the root (empty pointer; the `oneOf`) | each item of every event type's `examples` (event types only, never shared parts; so every event example is also a valid "any event") |
| `api-*.yml` | `/components/schemas/<Name>` | each item of its `examples` |
| `api-*.yml` | `/paths/<escaped path>/<method>/requestBody/content/<escaped media type>/schema` | each `examples.<key>.value` of that media type |
| `api-*.yml` | `/paths/<escaped path>/<method>/responses/<status>/content/<escaped media type>/schema` | each `examples.<key>.value` of that media type |
| `api-*.yml` | `/components/requestBodies/<Name>/content/<escaped media type>/schema` | each `examples.<key>.value` of that media type |
| `api-*.yml` | `/components/responses/<Name>/content/<escaped media type>/schema` | each `examples.<key>.value` of that media type |

(Escaping per RFC 6901: `~` as `~0`, `/` as `~1`.) A `requestBody` or response given as a `$ref` to
`components/` is checked at its target location (the component rows above), once. Any validation error is a failure.

### Task specs
Every `docs/tasks/*.yml` MUST parse (same loader, duplicate keys rejected), have a mapping root, and have `id`
equal to the file name without `.yml`.

### Checker interface
- `python3 scripts/ci/check_contracts.py` checks the repo it is run in (contracts and task specs);
  `--root <dir>` checks another tree. Exit 0 if no failures, 1 if any. Each failure is one line:
  `<file>: <JSON pointer or line>: <message>`.
- `--self-test` runs the checker against the fixtures in `scripts/ci/fixtures/contracts/`: at least one tree that
  must pass and one failing tree per MUST rule above; exit 0 only if every fixture gives the expected result.
- Needs `pyyaml`, `jsonschema[format-nongpl]` and `openapi-spec-validator`, at exact versions pinned in
  `scripts/ci/requirements-contracts.txt`; `.github/workflows/ci.yml` installs from that file. If a package is
  missing, exit 2 with `python3 -m pip install -r scripts/ci/requirements-contracts.txt`; never skip a check.

## Conventions
- Service names, everywhere (file names, `info.title`, event `source`): `pipeline-runner`, `artifact-store`,
  `release-service`, `dashboard`.
- Contract objects set `additionalProperties: false` (or `unevaluatedProperties: false` when composed, see
  "Composition") unless a field is meant to be open (say why in its `description`), so a misspelt field in an
  example fails the check.
- Statuses in the task table: `todo`, `in-progress`, `blocked`, `in-review`, `unverified`, `done` (`done` set only
  by the lead). Task branches may only change their own `files_touched`, so status updates to this table are made
  by the lead on a housekeeping branch (`spec-T<nn>-...`).
- CI: third-party GitHub Actions pinned by commit SHA; pip packages pinned to exact versions.
- Contracts are frozen once T012 merges; changes go through the lead (table below). The T020 changes are the
  last between waves 1 and 2; from the start of T021 to the end of wave 2 only a Blocking defect changes them.
- Wave 2 setup (ports, env vars, data dir, scripts, `pyproject.toml` tables, CI) is `docs/team/environment.md`
  § "Wave 2 setup (T019, approved)"; task specs do not restate it.
- Write endpoints commit the database transaction before they send the response; events are sent only after the
  commit, from a background task, so a slow or down dashboard never delays or changes a response or an outcome
  (Q-11 default).
- Event senders (pipeline-runner, artifact-store, release-service) behave the same: a new `event_id` (UUID) per
  event, reused on every retry; up to 3 attempts with 2 s timeout each, waiting 0.5 s and then 1 s; retry only on
  a network error, a timeout or a 5xx; then log and drop. Sending never raises into the caller.
- Error precedence is the one in each operation's description; where none is stated: 422 for a malformed path or
  query parameter, then 404, then 422 for the body, then 409.
- No new package in wave 2 unless the task's spec lists its `pyproject.toml` and `uv.lock` and the reviewer
  agrees; tests fake other services with `httpx.MockTransport` (part of httpx), not a new mocking library.
- Every service task proves its decisions with the named tests in its spec (pytest node IDs, so a missing test
  fails the acceptance command), validates real responses against the contract schemas in its tests, and keeps
  coverage at or above `fail_under` (proposed by T021, confirmed by the lead).

## Tasks

Owner, branch, dependencies and `read_first` are in each `docs/tasks/Tnn.yml`.

| ID | Task | Acceptance (runnable command; reading of the brief, Q-08) | Files touched | Status |
| --- | --- | --- | --- | --- |
| [T010](tasks/T010.yml) ([#9](https://github.com/regevha/shipyard/issues/9)) | Wave 1 plan, contract file format, task specs, open questions | `python3 -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('docs/tasks/*.yml')]; print('ok')"` prints `ok`; the disjoint check in `docs/tasks/T010.yml` prints `disjoint` | `docs/PLAN.md`, `docs/OPEN_QUESTIONS.md`, `docs/tasks/T010.yml`, `docs/tasks/T011.yml`, `docs/tasks/T012.yml` | done (PR #12, a265a4f) |
| [T011](tasks/T011.yml) ([#10](https://github.com/regevha/shipyard/issues/10)) | CI: contract and task-spec checker, aggregate `ci-ok` job | `python3 scripts/ci/check_contracts.py --self-test` exits 0; `python3 scripts/ci/check_contracts.py` exits 0; `ci-ok` check run is `success` on the PR head and on `main` (command in `T011.yml`) | `.github/workflows/ci.yml`, `scripts/ci/check_contracts.py`, `scripts/ci/requirements-contracts.txt`, `scripts/ci/fixtures/contracts/**` | done (PR #51, 50d9498; `ci-ok` required in ruleset Main1 since 2026-11-26: Q-06) |
| [T012](tasks/T012.yml) ([#11](https://github.com/regevha/shipyard/issues/11)) | Wave 1 contracts: events, errors, four service APIs; open questions updated | `python3 scripts/ci/check_contracts.py` exits 0; the file-presence loop in `T012.yml` exits 0; reviewer APPROVE on cross-service consistency (review gate, not a command) | `contracts/events.yml`, `contracts/errors.yml`, `contracts/api-pipeline-runner.yml`, `contracts/api-artifact-store.yml`, `contracts/api-release-service.yml`, `contracts/api-dashboard.yml`, `docs/OPEN_QUESTIONS.md` | done (PR #84, af3a864; full reviewer APPROVE after 2 fix rounds) |
| [T013](https://github.com/regevha/shipyard/issues/38) ([#38](https://github.com/regevha/shipyard/issues/38)) | Store the user's brief verbatim (`docs/BRIEF.md`); check every "brief" citation against it; label the lead's own choices as assumptions (Q-25..Q-27) | `python3 scripts/team/check_brief_quotes.py --self-test` and `python3 scripts/team/check_brief_quotes.py` exit 0: every double-quoted passage (12+ characters, outside code) in `docs/OPEN_QUESTIONS.md` and `docs/PLAN.md` is word for word in `docs/BRIEF.md`, or is a section name, is labelled as a paraphrase, or is declared with its source in the script's `OTHER_SOURCES`; every `resolved-by-user-brief` entry has a Brief (verbatim) bullet with a quote found in the brief; reviewer APPROVE (review gate, not a command) | `docs/BRIEF.md`, `docs/OPEN_QUESTIONS.md`, `docs/PLAN.md`, `scripts/team/check_brief_quotes.py` | done (PR #39, 741e554) |
| T014 ([#73](https://github.com/regevha/shipyard/issues/73)) | Contract file format amendments from the T011 review (#53, #57, #65, #67, #71, #72): error-response media type, non-JSON YAML values and merge keys, outermost-composer rule, allowed `$ref` forms and scanning, no network | `python3 -I scripts/team/check_brief_quotes.py` exits 0; reviewer APPROVE (review gate, not a command) | `docs/PLAN.md` | done (PR #74, 5a8c2a5) |
| T015 ([PR #80](https://github.com/regevha/shipyard/pull/80)) | Correct Q-06 (ruleset Main1); T011, T013, T014 done | `python3 -I scripts/team/check_brief_quotes.py` exits 0; reviewer APPROVE (review gate) | `docs/OPEN_QUESTIONS.md`, `docs/PLAN.md` | done (PR #80, 7d8362c) |
| T016 ([PR #114](https://github.com/regevha/shipyard/pull/114)) | Wave 1 close-out: T012 done, Q-34, stale wording (#113, #81, #82, #83) | `python3 -I scripts/team/check_brief_quotes.py` exits 0; `python3 scripts/ci/check_contracts.py` exits 0; reviewer APPROVE (review gate) | `docs/OPEN_QUESTIONS.md`, `docs/PLAN.md` | done (PR #114, 218c401) |
| [T017](tasks/T017.yml) ([#116](https://github.com/regevha/shipyard/issues/116)) | Contracts apply the user's decisions of 2026-11-26 (Q-23, Q-28..Q-35, Q-36; #112) | `python3 scripts/ci/check_contracts.py` and `--self-test` exit 0; the `x-assumed` grep in `T017.yml` exits 0; full reviewer finds no cross-file disagreement (review gate, not a command) | the six `contracts/*.yml` | done (PR #123, d3f0b12; full reviewer APPROVE after 1 fix round in each of its two review rounds (the second for #119 and #120)) |
| T018 ([#117](https://github.com/regevha/shipyard/issues/117)) | Record the user's decisions of 2026-11-26 in `docs/OPEN_QUESTIONS.md` (Q-03..Q-06, Q-24, Q-25, Q-27..Q-36; Q-23 resolved by T017), the Q-05 rule in `docs/team/shipyard-overrides.md`, this table | `python3 -I scripts/team/check_brief_quotes.py` and `--self-test` exit 0; reviewer APPROVE (review gate) | `docs/OPEN_QUESTIONS.md`, `docs/PLAN.md`, `docs/team/shipyard-overrides.md`, `scripts/team/check_brief_quotes.py` (one `OTHER_SOURCES` line) | done (PR #133) |
| [T019](tasks/T019.yml) ([#25](https://github.com/regevha/shipyard/issues/25)) | Wave 2 setup proposal (Q-03): SQLite and migration tool, start command, ports and slots, script names, per-service `pyproject.toml`, in `docs/team/environment.md`; the user approves before any service task | the commands in `T019.yml` (spec merged in PR #134); reviewer APPROVE and the user's approval on #25 (review gates) | `docs/team/environment.md` | done (PR #135, 357eb3f; approved by Nir on #25) |
| [T020](tasks/T020.yml) | Wave 2 plan and task specs T021-T028; environment.md marked approved (#36, #136); contract changes #121 (newline guard) and #136 (no contract change) | the commands in `T020.yml`: every spec parses, sub-wave `files_touched` disjoint, `read_first` targets exist, every contract `pattern` guarded, `check_contracts.py` and `--self-test` exit 0, `check_brief_quotes.py` exits 0; reviewer APPROVE (review gate) | `contracts/events.yml`, `docs/PLAN.md`, `docs/team/environment.md`, `docs/tasks/T020.yml`..`T028.yml`, `docs/tasks/T020.md` | done (PR #137, merge f779826; 1 fix round) |
| [T021](tasks/T021.yml) | 2a. Scaffold (devops): `.gitignore` (#8), four service projects + `stack-tests/` (pyproject, `uv.lock`, `.python-version`), minimal `app/main.py` + `tests/test_main.py`, dashboard placeholder `static/index.html`, `scripts/dev/*.sh` (#136), `check_shared_copy.py`, CI matrix + shared-copy job in `ci-ok`; proposes `fail_under` | the commands in `T021.yml` (per-service uv/ruff/mypy/pytest, stack start/stop in a spare slot incl. the #136 refuse case, `check_shared_copy.py --self-test`, `ci-ok` success); lead confirms `fail_under` (review gate) | see `T021.yml` | done (PR #151, merge 92980c2; 2 fix rounds) |
| [T022](tasks/T022.yml) | 2a. Shared modules (backend-dev): `shared/errors.py` (Q-21, #136 mapping), `shared/openapi_conformance.py` (Q-22), their tests, verbatim copies in all four services | named pytest node IDs in every service; `check_shared_copy.py` exits 0 with no file pending | `shared/**`, `services/*/app/errors.py`, `services/*/tests/openapi_conformance.py`, `services/*/tests/test_shared_*.py` | done (PR #156, merge 818c588; 0 fix rounds) |
| [T023](tasks/T023.yml) | 2b. dashboard backend (backend-dev): `POST /events` intake, `GET /builds`, `/artifacts`, `/releases`, static mount; read-only (Q-23, Q-32); `assumed (#131)` | named pytest node IDs, conformance test, coverage; `DATA_MODEL.md`, hand-off | `services/dashboard/` except `static/` and the T022 copies | done (PR #162, merge 480f8a9; 1 fix round) |
| [T024](tasks/T024.yml) | 2b. pipeline-runner (backend-dev): `POST /runs`, `GET /runs/{build_id}` (Q-28), simulated steps (Q-33), one fake upload (Q-34, Q-36/#120), name rule (#119), events; upload timeout (#132) | named pytest node IDs, conformance test, coverage; timeout in hand-off | `services/pipeline-runner/` except the T022 copies | done (PR #164, merge 3d60a7f; 1 fix round) |
| [T025](tasks/T025.yml) | 2b. artifact-store (backend-dev): upload with version and SHA-256 (Q-17), checksum header, 413, name rule (Q-29), download, blobs under the data dir, `artifact.uploaded` | named pytest node IDs, conformance test, coverage | `services/artifact-store/` except the T022 copies | done (PR #161, merge 7ce3379; 2 fix rounds) |
| [T026](tasks/T026.yml) | 2c. release-service (backend-dev): request with `requested_by` (Q-30), final decision (Q-10), promote only if approved (Q-16), idempotent promote (Q-31), events, no promotion event (Q-14) | named pytest node IDs, conformance test, coverage | `services/release-service/` except the T022 copies | done (PR #169, merge 70dde03; 2 fix rounds) |
| [T027](tasks/T027.yml) | 2c. dashboard UI (frontend-dev): `services/dashboard/static/` builds, failures, artifacts, releases; auto-refresh; no buttons (Q-32); only the dashboard's own JSON (Q-23); `assumed (#131)` | the grep checks in `T027.yml`; browser smoke test against the real dashboard and ux-reviewer (review gates) | `services/dashboard/static/**` | done (PR #168, merge 2fc966c; 2 fix rounds, UX review too) |
| [T028](tasks/T028.yml) | 2d. Stack tests and demo (tester): `stack-tests/` full flow, failed step, failed upload, bad name; CI `stack` job in `ci-ok`; `docs/DEMO.md` | `uv run pytest` in `stack-tests/`; the DEMO walkthrough block runs; `ci-ok` success | `stack-tests/**`, `.github/workflows/ci.yml`, `docs/DEMO.md` | done (PR #174, merge 3456c31; 0 fix rounds) |

## Contract change requests

| Date | From | Change | Status |
| --- | --- | --- | --- |
| 2026-11-25 | reviewer (T012 verify, #112) | `contracts/api-pipeline-runner.yml` info: cite #110 / Q-34 in the sentence on which artifacts a run uploads (wording only) | applied in T017 (PR #123) |
| 2026-11-26 | architect (T017 finding, #121) | `contracts/events.yml` `Checksum` and `Timestamp`: add `not: {pattern: "\n"}`, the guard T017 gave `ArtifactName` (Python `re` lets `$` match before a final newline); they were the only unguarded `pattern`s in the six files (`PipelineName` refers to `ArtifactName`) | applied in T020 |
| 2026-11-26 | reviewer (T019 review, #136) | Error mapping in `shared/errors.py`: any framework 4xx without its own code answers 422 `validation_failed`, any 5xx answers 500 `internal_error`. Chosen over adding (status, `validation_failed`) pairs to `errors.yml` `x-status-codes`: no contract change, every status a service can emit stays listed in `x-status-codes`, and no operation would list the new statuses, so the conformance test (Q-22) needs nothing extra | decided in T020, no contract change; written into `docs/team/environment.md` (Error envelope row) and `T022.yml` |
