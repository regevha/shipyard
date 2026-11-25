# Task files

Each task has up to two files here, with different writers so they never collide.

| File | Written by | Purpose |
| --- | --- | --- |
| `Tnn.yml` | `architect` | The task's spec, read by the lead's overlap gate and (later) CI |
| `Tnn.md` | the task's owner | Hand-off note: what was built, the interface it exposes, what the next agent needs |

## `Tnn.yml` format

```yaml
id: T07
title: Jobs list endpoint
owner: backend-dev          # db-engineer | backend-dev | frontend-dev | tester | e2e-tester | devops | chore
branch: T07-backend-jobs   # must start with the task ID (T<nn>- or T<nn>_); CI fails branch names without a task ID, except prefixes listed in docs/team/branch_exemptions
wave: 2
depends_on: [T03, T05]
migration: false            # true for at most one task per wave
files_touched:              # complete list, globs allowed; include wiring files and lockfiles
  - server/app/routers/jobs.py
  - server/app/repos/jobs.py
  - server/app/main.py
read_first:                 # exact files (and doc sections) the agent needs; the lead pastes this into the prompt
  - docs/API.md#jobs
  - server/app/repos/jobs.py
  - docs/tasks/T05.md         # hand-offs of the tasks it depends on
mode: team                  # team | direct (direct = lead-made small change; see "Team or direct" in docs/team/lead.md)
ui: false                   # true only if the task changes what a user sees; gates screenshots, browser smoke test and ux-reviewer
acceptance: [AC-04, AC-05]  # AC-nn IDs from docs/PRODUCT.md
issue: 12                   # GitHub issue number, once it exists
```

## `read_first` and `ui`

- `read_first` keeps agent context small: list only what the agent must read (files, or `doc#section`), including the
  hand-off notes of its `depends_on` tasks. Agents read this list instead of exploring or loading the whole plan.
- `ui: true` turns on screenshots, the browser smoke test and the `ux-reviewer`. Backend, data, test, CI and docs tasks
  are `ui: false` and skip all three.

## Overlap rule

Two tasks in the same wave must have disjoint `files_touched`. The lead and `project-manager`
check this before each wave.

## `Tnn.md` hand-off note

Short: what was built, the interface provided, decisions made, anything the next agent must know.
