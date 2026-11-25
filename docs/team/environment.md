# Environment (Shipyard)

Read by agents that run code: build agents, `tester`, `e2e-tester`, `reviewer`, `devops`, `ux-reviewer`. The lead also pastes the layout map below into the prompt of every agent, including `product-manager`, `project-manager` and `chore`, which do not read this file. This file is specific to Shipyard and is not synced from the shared core.

## Decided by the user
- Python + FastAPI for every service.
- Services talk over plain HTTP at first; a real event queue comes later.
- One repo, one folder per service: `services/<name>/`.
- Planned services: `pipeline-runner`, `artifact-store`, `release-service`, `dashboard`.

## Proposed by the lead (confirm or change in wave 0; until then treat as a working assumption, not a decision)
- Each service owns its own data, with no shared database, and a service uses another service only through its contract.
- Contracts avoid assuming a call is synchronous, so the queue can replace calls later.
- Contract files, one owner each: `docs/contracts/<service>/API.md` (architect) and `docs/contracts/<service>/DATA_MODEL.md` (db-engineer), plus `docs/contracts/SHARED.md` (architect) for ids, statuses, the error format and who calls whom.
- `e2e/`: browser flows through the dashboard belong to `e2e-tester`; stack-level HTTP tests that start several services belong to `tester`. Wave 0 confirms.

## Open (do not assume)
Database engine and migration tool per service; how the stack starts locally (compose or plain processes); whether the dashboard is server-rendered or a separate frontend; authentication between services. The stack defaults named in the synced agent files (PostgreSQL, Alembic, React + Vite, Vitest) do not apply to Shipyard until wave 0 decides.

## Layout map for the synced team files
The synced files (`CLAUDE.md`, `docs/team/lead.md`, `.claude/agents/`, `docs/tasks/README.md`) were written for one `server/` + `web/` app. In Shipyard read their paths like this:
- `server/` means `services/<service>/` for the service the task names, with the same inner shape: `app/` (data access in `app/repos/`), `db/` if the service has a database, `tests/`.
- `web/` means the dashboard's UI code. Its folder is decided in wave 0 with the open dashboard question. Until then `backend-dev` owns the dashboard's `app/` and `frontend-dev` owns only the UI folder the architect names; neither edits the other's folder.
- `docs/API.md` and `docs/DATA_MODEL.md` mean the per-service files above; the shared contract is `docs/contracts/SHARED.md`. All are frozen during a wave and change only through the lead. `project-manager`, `chore` and `product-manager` treat every file under `docs/contracts/` as a contract.
- The "Team or direct" module list in `lead.md` counts modules per service (`services/<s>/app/<package>`, `services/<s>/db/`, `services/<s>/tests/`), and any change that touches two services' code or contracts counts as large.
- Lockfiles: one per service (`services/<s>/uv.lock`, and the UI's lockfile if it has one). The "one agent per side" rule becomes one agent per service.
- In `docs/tasks/Tnn.yml`, `files_touched` and `read_first` use the real paths, for example `services/pipeline-runner/app/**` and `docs/contracts/pipeline-runner/API.md#runs`. CI checks those, not this map.

## Commands
Per service, from `services/<service>/`: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy`, which needs `[tool.mypy] files = [...]` in that service's `pyproject.toml` (without it mypy exits with an error). Each service's `pyproject.toml` and the stack-level start command are created in wave 0 and recorded here. Export any database URL variables on every shell call (the environment does not persist).

## Worktrees, ports and databases
- Work in your own git worktree on the branch named in your task spec. Commit locally; never push.
- Ports: the lead assigns each agent a slot. A slot has one port per service, in the service order above; the port base and the exact numbering are set by devops in wave 0 and written here (TBD). Do not invent port numbers before then.
- Databases: name them `shipyard_<task>_<agent>_<service>` with every hyphen written as an underscore (for example `shipyard_t012_backend_dev_pipeline_runner`), one per service you start. State in your report that ports and databases were cleaned up.
- Never run two agents at once that edit files the other one tests or builds on. A contract change request goes to the lead with the list of consuming services and their tests.
- Put scratch files (downloaded tools, tarballs) in `/tmp`, never in the repo.
