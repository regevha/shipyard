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

**Wave 2: the four services, built against the contracts (outline only, no specs yet; the wave 2/3 split is the lead's
outline, not the brief's, Q-27).** Starts with the decisions
listed as "wave 0" in `docs/team/environment.md` (Q-03). Rough task list, at most 3 build agents at a time, so it
will likely split into 2a and 2b:
- Setup (devops): per-service `pyproject.toml` and lockfile, port base and slot numbering, local start command,
  CI jobs per service, `environment.md` update (Q-01, Q-02, Q-03).
- Per service (backend-dev): `dashboard` events intake + read API; `pipeline-runner`; `artifact-store`;
  `release-service`. Each with its own tests and a conformance test against its `contracts/api-<service>.yml`
  (how FastAPI's generated OpenAPI is compared: Q-22).
- Dashboard UI (frontend-dev): static HTML + JS pages served by the dashboard (folder: Q-02).
- Stack-level HTTP test (tester): start all four, run a pipeline, upload, request, approve, promote, check the
  dashboard read API.

**Wave 3: hardening (outline only; lead's outline, Q-27).** Replace the HTTP event calls with a real queue (the
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
- The self-test has one failing fixture per case: an unquoted integer key, an unquoted timestamp value, an unquoted
  date value, and an unquoted `on` where the schema says `type: string`.

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
- Composition: a schema built with `allOf` MUST close itself with `unevaluatedProperties: false` at the composing
  level, and MUST NOT have `additionalProperties: false`; a schema used as an `allOf` member (inline, or as the
  target of a `$ref` inside `allOf`) MUST NOT have `additionalProperties: false` or `unevaluatedProperties: false`
  (it stays open, so the composer's own keyword decides). The checker fails on each breach. This rule applies to
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
- Every response whose status is `4XX`, `5XX` or a number from 400 to 599 MUST use media type
  `application/json` with `schema: {$ref: "errors.yml#/$defs/ErrorEnvelope"}` (nothing else in that schema), and
  each numeric error status MUST appear as a `status` in `errors.yml#/x-status-codes`. Status keys are quoted
  strings (see "YAML must load as JSON").
- `default` responses are not allowed (list the statuses).

### References
- Inside a file: JSON pointers from its root, e.g. `#/$defs/BuildStarted`, `#/components/schemas/Artifact`.
- Across files: the relative form `<file>#<pointer>`, e.g. `errors.yml#/$defs/ErrorEnvelope`,
  `events.yml#/$defs/BuildFinished`. It resolves against the base URI, so it names one of the six files.
- Any `$ref` that does not resolve to a location inside one of the files under `contracts/` is an error. The
  checker never fetches anything over the network. OpenAPI `$ref`s outside schemas (to `components/responses`,
  `components/parameters`, `components/examples`) follow the same rules.

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
- Contracts are frozen once T012 merges; changes go through the lead (table below).

## Tasks

Owner, branch, dependencies and `read_first` are in each `docs/tasks/Tnn.yml`.

| ID | Task | Acceptance (runnable command; reading of the brief, Q-08) | Files touched | Status |
| --- | --- | --- | --- | --- |
| [T010](tasks/T010.yml) ([#9](https://github.com/regevha/shipyard/issues/9)) | Wave 1 plan, contract file format, task specs, open questions | `python3 -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('docs/tasks/*.yml')]; print('ok')"` prints `ok`; the disjoint check in `docs/tasks/T010.yml` prints `disjoint` | `docs/PLAN.md`, `docs/OPEN_QUESTIONS.md`, `docs/tasks/T010.yml`, `docs/tasks/T011.yml`, `docs/tasks/T012.yml` | done (PR #12, a265a4f) |
| [T011](tasks/T011.yml) ([#10](https://github.com/regevha/shipyard/issues/10)) | CI: contract and task-spec checker, aggregate `ci-ok` job | `python3 scripts/ci/check_contracts.py --self-test` exits 0; `python3 scripts/ci/check_contracts.py` exits 0; `ci-ok` check run is `success` on the PR head and on `main` (command in `T011.yml`) | `.github/workflows/ci.yml`, `scripts/ci/check_contracts.py`, `scripts/ci/requirements-contracts.txt`, `scripts/ci/fixtures/contracts/**` | in-review |
| [T012](tasks/T012.yml) ([#11](https://github.com/regevha/shipyard/issues/11)) | Wave 1 contracts: events, errors, four service APIs; open questions updated | `python3 scripts/ci/check_contracts.py` exits 0; the file-presence loop in `T012.yml` exits 0; reviewer APPROVE on cross-service consistency (review gate, not a command) | `contracts/events.yml`, `contracts/errors.yml`, `contracts/api-pipeline-runner.yml`, `contracts/api-artifact-store.yml`, `contracts/api-release-service.yml`, `contracts/api-dashboard.yml`, `docs/OPEN_QUESTIONS.md` | todo |
| [T013](https://github.com/regevha/shipyard/issues/38) ([#38](https://github.com/regevha/shipyard/issues/38)) | Store the user's brief verbatim (`docs/BRIEF.md`); check every "brief" citation against it; label the lead's own choices as assumptions (Q-25..Q-27) | `python3 scripts/team/check_brief_quotes.py --self-test` and `python3 scripts/team/check_brief_quotes.py` exit 0: every double-quoted passage (12+ characters, outside code) in `docs/OPEN_QUESTIONS.md` and `docs/PLAN.md` is word for word in `docs/BRIEF.md`, or is a section name, is labelled as a paraphrase, or is declared with its source in the script's `OTHER_SOURCES`; every `resolved-by-user-brief` entry has a Brief (verbatim) bullet with a quote found in the brief; reviewer APPROVE (review gate, not a command) | `docs/BRIEF.md`, `docs/OPEN_QUESTIONS.md`, `docs/PLAN.md`, `scripts/team/check_brief_quotes.py` | in-review |

## Contract change requests

| Date | From | Change | Status |
| --- | --- | --- | --- |
