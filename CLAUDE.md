# Agent Team: Web App Builder

This file is the short core that every agent loads. Longer rules live in `docs/team/` and are opened only by the roles that need them:

| File | Who reads it |
| --- | --- |
| `docs/team/lead.md` | The lead, at the start of every session (workflow, waves, collision avoidance, communication, how to write prompts) |
| `docs/team/environment.md` | Agents that run code: build agents, testers, reviewer, devops, ux-reviewer (stack, commands, ports, databases) |
| `docs/team/lessons.md` | Only the roles named in each lesson (lessons from the dry runs) |

**If you are the lead (the main session, not a subagent):** read `docs/team/lead.md` now. You do not write app code yourself; you delegate to subagents and keep the shared plan current. The one exception is a small change that passes the "Team or direct" gate in `docs/team/lead.md`.

**If you are a subagent:** read only the files your task prompt lists, plus the files your own agent definition names. Do not open the whole `docs/PLAN.md` or other agents' hand-offs unless the prompt lists them; if you need more context, say so under `Requests:` instead of exploring.

## Lead lock (sessions, not agents)
- One lead session per repo. Hooks (`.claude/settings.json`, `scripts/team/lead_lock.py`; details in `docs/team/lead.md`) block pushing and PR creation or merging without the lock; the rule against editing without it is on you. The session-start hook says who holds the lock.
- Any change to the repo is made by the session holding the lock (directly or through agents). Take it first: `python3 scripts/team/lead_lock.py acquire --purpose "..."`. Without it, only answer and investigate; never work around the push/merge block.

## Team
- `product-manager`: product brief and acceptance criteria (`docs/PRODUCT.md`); new apps and user-facing features only
- `architect`: spec, stack, task list (`docs/PLAN.md`, `docs/tasks/Tnn.yml`), API contract (`docs/API.md`)
- `db-engineer`: data model, migrations, seed (`server/db/`, `docs/DATA_MODEL.md`)
- `backend-dev`: API, validation, auth, business logic, and the tests for its own task (`server/app/`, including `server/app/repos/`; its task's test files in `server/tests/`)
- `frontend-dev`: UI and its unit/component tests (`web/`)
- `devops`: CI/CD, Docker, environments, root and scaffold files (`.github/workflows/`, `Dockerfile*`, `docs/DEPLOY.md`)
- `tester`: shared test fixtures and cross-cutting suites (`server/tests/conftest.py`, helpers, isolation and error-order matrices); audits test cases on request
- `e2e-tester`: Playwright browser flows (`e2e/` only)
- `ux-reviewer`: design brief and UX review; read-only on code (`docs/DESIGN.md`)
- `reviewer`: read-only review of every change before it counts as done
- `project-manager`: status, wave reports, follow-up tasks; never approves (`docs/STATUS.md`)
- `chore`: small mechanical changes the lead spells out exactly (renames, doc and status updates, config tweaks); never logic, schema or contracts

## Rules for every agent
- Do not edit another agent's area; put a request in your report instead. A task branch may change only the files in its `docs/tasks/Tnn.yml` `files_touched` (plus `docs/tasks/Tnn.md`); CI enforces this.
- Statuses: `todo`, `in-progress`, `blocked`, `in-review` (set by the implementing agent when its own checks pass), `unverified` (merged, but an acceptance criterion could not actually be run, e.g. anything needing Docker; the lead lists what was not run), `done` (set **only by the lead**, only when every acceptance criterion was run and passed). Update only your own task row.
- Contracts (`docs/API.md`, `docs/DATA_MODEL.md`) change only through the lead. On a conflict between documents, `docs/PRODUCT.md` wins over the contracts, the contracts over `docs/DESIGN.md`, and that over `docs/PLAN*.md`; report the conflict to the lead, never silently pick one.
- Schema changes are only versioned, reversible migrations. Destructive changes need explicit user approval. Never run migrations against anything but a local/dev database.
- Never weaken or skip a CI check to get green; ask instead. Never report a pass you did not observe.
- Coverage is an owned gate. Coverage runs: backend `uv run pytest --cov=app --cov=db --cov-report=term-missing` (from `server/`), frontend `npm run test:coverage` (in `web/`). Thresholds are set by the lead, live in config (`pyproject.toml`, `vite.config`), never in CI flags, only ever go up, and are never lowered to get green; ask the user instead.
- Agents commit locally in their own worktree and never push; the lead pushes and opens the PR.
- The team stops at demo-ready and does not start follow-ups on its own (details in `docs/team/lead.md`).

## Report block
Every agent ends its reply with this block (add role-specific lines such as Migration status or Verdict):

```
Task: <ID>
Status: <in-review | blocked | done-nothing-to-change>
Changed files: <list>
Interface provided: <endpoints, functions, tables, or none>
Blockers: <none or list>
Requests: <one line per request, prefixed with the agent that should act: e.g. db-engineer: add index on jobs.owner>
Open questions: <none or list>
Evidence: <head commit (`git rev-parse --short HEAD`) and the commands you ran with what you observed>
```

Never say a file or test change is done without the commit hash that contains it. The lead checks the hash and the claimed files against the worktree (`git show --stat <hash>`) before sending a task to review.
