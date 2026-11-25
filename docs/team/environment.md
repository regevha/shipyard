# Environment (Shipyard)

Read by agents that run code: build agents, `tester`, `e2e-tester`, `reviewer`, `devops`, `ux-reviewer`. This file is specific to Shipyard and is not synced from the shared core.

## Stack (user decisions)
- One stack for every service: Python + FastAPI. Services talk over plain HTTP at first; a real event queue may replace some calls later, so contracts must not depend on a call being synchronous.
- One repo, one folder per service: `services/<name>/`. Planned services: `pipeline-runner`, `artifact-store`, `release-service`, `dashboard`. Each service owns its own data and exposes only its contract; no shared database, no reading another service's code.
- Decided in wave 0 (not yet decided; do not assume): database engine and migration tool, how the stack starts locally (compose or plain processes), whether the dashboard is server-rendered or a separate frontend, authentication between services.

## Layout map for the shared team files
The synced files (`CLAUDE.md`, `docs/team/lead.md`, `.claude/agents/`, `docs/tasks/README.md`) were written for a single `server/` + `web/` app. In Shipyard read their paths like this:
- `server/` means `services/<service>/` for the service the task names (inside it the same shape: `app/`, `db/` if the service has a database, `tests/`).
- `web/` means the dashboard's UI code, under `services/dashboard/`.
- `docs/API.md` and `docs/DATA_MODEL.md` mean the per-service contracts under `docs/contracts/<service>.md`, plus one shared contract document for ids, statuses, errors and who calls whom. They are frozen during a wave and change only through the lead.
- `e2e/` holds the stack-level tests that start several services.
- A task's `docs/tasks/Tnn.yml` `files_touched` always spells out the real paths; CI checks those, not this map.

## Commands
Per service, from `services/<service>/`: the service's own `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`. The architect and devops fix the exact commands and the stack-level start command in wave 0 and write them here. Export any database URL variables on every shell call (the environment does not persist).

## Worktrees, ports and databases
- Work in your own git worktree on the branch named in your task spec. Commit locally; never push.
- Several services run at once, so each agent gets a port range, not one port: the lead assigns a slot and the base is `base + slot * 10`, one port per service in a fixed order (devops records the order). Use a database named `shipyard_<task>_<agent>` per service you start. State in your report that ports and databases were cleaned up.
- Never run two agents at once that edit files the other one tests or builds on. A contract change request goes to the lead, with the list of consuming services and their tests.
- Put scratch files (downloaded tools, tarballs) in `/tmp`, never in the repo.
