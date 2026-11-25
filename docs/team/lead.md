# Lead playbook

Read by the lead at the start of every session. Subagents do not need this file.

## Team or direct (decide before any work)
Use the team only when the change is large. A change is **large** if **any** of these is true; check each against the diff you expect, not a feeling:

1. It touches more than 2 modules. A module is one of: `server/app/<package>` (e.g. `routers`, `repos`, `services`), `server/db/`, `server/tests/`, `web/src/<top-level folder>`, `e2e/`, `.github/` (CI), `docs/` contracts (`API.md`, `DATA_MODEL.md`, `PRODUCT.md`).
2. It needs a migration (any change under `server/db/migrations/` or to a model).
3. It adds an endpoint, or changes an endpoint's request, response or errors (anything that changes `docs/API.md`).
4. It adds or upgrades a package (`uv.lock`, `package-lock.json`).
5. It is a new user-facing feature (it would need acceptance criteria in `docs/PRODUCT.md`).
6. It touches auth, permissions, or data deletion.

If none is true, the lead makes the change **directly**. If you are unsure about any item, treat it as true.

**A direct change still goes through the rules:**
- Write a short `docs/tasks/Tnn.yml` first (`mode: direct`, `files_touched`, `ui`, acceptance in one or two lines), so the CI scope check applies. Work on a `Tnn-...` branch and open one PR.
- Run the relevant checks from `docs/team/environment.md` yourself and list them in the PR.
- Approval and green CI are still required before merge, from the reviewer the by-risk rule picks (`reviewer-light` for plain direct changes; `reviewer` if it escalates or if the change is CI, rules or an evidence document). Give it a short prompt: the diff, the task spec, and "no browser or screenshots needed" unless `ui: true`.
- Write the hand-off note `docs/tasks/Tnn.md` (a few lines is enough).
- **Escalate mid-way:** if the diff grows and any gate item becomes true, stop, keep the branch, and hand the task to the team (architect first). Never finish a large change directly.
- Record `mode: direct` or `mode: team` in the PR description so the split can be checked later.

## Models (set in each agent's frontmatter, never per call)
- `opus`: `product-manager`, `architect`, `reviewer`, `db-engineer`, `ux-reviewer`, `tester`, `e2e-tester`. A mistake in scope, acceptance criteria, plans, reviews, schema or design is expensive downstream; `product-manager` and `architect` also run only a few times per feature.
- `sonnet`: build agents (`backend-dev`, `frontend-dev`), `devops` and `reviewer-light`.
- **Which reviewer (by risk, not by mode):** `reviewer` (opus) for any change to behaviour (API, UI, CI, migrations, auth, permissions, data deletion, packages) and for any document that serves as evidence or is a source of truth (lessons and wave reports, contracts, specs, plans, rules and agent definitions). `reviewer-light` (sonnet, same rules) for `mode: direct` tasks, `chore` output, and docs-only changes that are plain status or wording (status tables, README wording, typos). **Risk wins over mode:** a `mode: direct` change that is CI, rules or agent definitions, or an evidence document still goes to `reviewer`. If `reviewer-light` returns `ESCALATE`, or finds a real problem in a document, send the same commit to `reviewer`. A `mode: team` task that is docs-only and plain status or wording may use `reviewer-light`; say so in the PR description. Reason: in the Task Manager run the full reviewer found five wrong facts in the lessons report, so evidence documents keep the full reviewer, while status edits do not need it.
- `haiku`: `project-manager` (status and reports) and `chore` (mechanical edits).
Hand a change to `chore` only when you can state the exact edit (files, old and new names or text) and it touches no logic, schema, contract or test assertion. Otherwise it goes to the owning agent.

## Writing agent prompts (keep context small)
Most of the team's cost is agents re-reading context, so every delegation is short and exact:

1. **An exact file list, never "read the code around X".** Every prompt starts with a `Read first:` list taken from the task's `docs/tasks/Tnn.yml` `read_first` (plus anything you add), e.g. "Read these 4 files and the hand-off of T61: `server/app/routers/jobs.py`, `server/app/repos/jobs.py`, `docs/API.md` §Jobs, `docs/tasks/T61.md`". If `read_first` is missing, ask the architect to add it before launching.
2. **Excerpts, not whole documents.** Paste the task's own spec (`Tnn.yml`) and the `PLAN.md` rows of the tasks it depends on or blocks, and name the sections of `docs/API.md` / `docs/DATA_MODEL.md` / `docs/PRODUCT.md` that apply (e.g. "API.md: Conventions → Error precedence; Jobs"). Do not hand an agent the whole plan. Always include the neighbouring tasks' rows and hand-off paths: collisions come from the tasks next door.
3. **Name the extra team files the role needs**: `docs/team/environment.md` for anyone who runs code, and the relevant entries of `docs/team/lessons.md`.
4. **Screenshots and browser checks only for UI tasks.** A task with `ui: true` in its spec gets the browser smoke test, the `ux-reviewer` and screenshots in review. A task with `ui: false` (backend, data, tests, CI, docs) gets none of them; say "no browser or screenshots needed" in the reviewer's and tester's prompts.

## Workflow (every feature)
0. **Product** (new app or user-facing feature only): delegate to `product-manager` for `docs/PRODUCT.md`. Put its open product questions to the user in one batch and wait for answers (or record them as `assumed`) before planning.
1. **Plan**: delegate to `architect`, with `docs/PRODUCT.md` as input; every task's acceptance criteria must trace to an `AC-nn`. It writes/updates `docs/PLAN.md`, `docs/tasks/Tnn.yml`, `docs/API.md` and a draft `docs/DATA_MODEL.md`.
2. **Data**: if the feature changes data, `db-engineer` goes first: migration, model, seed. Backend work that needs it waits.
3. **Design** (tasks with `ui: true`): `ux-reviewer` writes the brief in `docs/DESIGN.md` first; `frontend-dev` builds to it. After the build, `ux-reviewer` reviews the running app alongside `reviewer`.
3b. **Build**: delegate independent tasks to `backend-dev` and `frontend-dev` in parallel. Tasks touching the same files run sequentially.
4. **Test**: the implementing agent writes and runs the tests for its own task (one test or more per acceptance criterion, plus an edge case each), and the `db-engineer` runs migrate up/down/up on a fresh DB. Its test files must be in the task's `files_touched`. Launch `tester` only for shared fixtures and cross-cutting suites (isolation matrix, error precedence, real-server smoke), or when the reviewer's test audit asks for it. For any task touching both `web/` and `server/`, also delegate to `e2e-tester` for the browser flow.
4b. **Check the report before review:** compare each agent's `Evidence:` with the worktree (`git show --stat <hash>`, changed files match the claim). A report without a commit hash is not ready for review; send it back.
5. **Review (one round)**: delegate to `reviewer`, which also audits the task's test cases against the acceptance criteria (see the reviewer's "Test audit"); for features with a brief, also `product-manager` for acceptance against the `AC-nn` list.
   - **APPROVE** → close.
   - **REQUEST CHANGES** → one fix round: resume the owning agent with the Blocking items only. Then resume the reviewer with a short prompt: "verify only these Blocking items on commit <sha>"; no full re-review, no new findings except regressions.
   - **Still blocking after the fix round** → it comes to the lead, not a third review. The lead decides: split the task, reassign it, change the spec through the architect, or ask the user. Record the decision on the task's issue.
6. **Close**: mark the task done in `docs/PLAN.md` only after test, review, green CI and (when there is a brief) product acceptance all pass.
7. **Report**: after each wave, delegate to `project-manager` with the agents' reports; it updates statuses, writes `docs/STATUS.md` and proposes the next wave. Only the lead sets `done`.
8. **Ship**: merged work deploys to staging via `devops` pipelines. Production deploys are manual and need the user's explicit go-ahead.

## Lead-only rules
- `docs/PLAN.md` is the single source of truth for status.
- Root and scaffold files (`.gitignore`, root README, tooling configs) belong to `devops`; the lead may create them when no devops task exists.
- Importing a declared interface across areas (e.g. `createApp`, `openDb`, `hashPassword`) is allowed. Changing such an interface needs a note in the PLAN.md "Contract change requests" section.
- When a fix lands for a defect a tester reported, send a follow-up to `tester` to remove `todo` flags and re-verify.
- Run the project-manager's plan-health check (file overlaps, missing dependencies, contradictions between docs, duplicate task IDs) before launching each wave.
- Max one fix round per review (see Workflow step 5); a tester or e2e defect also gets one fix round. After that the lead decides, and asks the user when the fix needs a product or spec change.
- **Stop at demo-ready (user decision):** the team's goal is a *demo-ready* app, then it stops and reports; it does not start further waves, follow-ups or nice-to-haves on its own. Demo-ready means: every must-have acceptance criterion in `docs/PRODUCT.md` is met (or, with no brief, every task of the first plan); no Blocking review items open; test, e2e and CI green; the app starts with one documented command and seed/demo data (`docs/DEMO.md`: how to run, demo login, a 5-minute walkthrough, known limitations). Deferred and later items are listed, not built. The lead then asks the user whether to continue.

## Collision avoidance (lead enforces)
- **One task, one worktree, one branch, one PR.** Each build agent works in its own git worktree on a branch named after its task (`T07-backend-jobs`) and opens one PR. Reviewer and tester check the PR's commit, never a tree that is still changing. Merge PRs one at a time, rebasing the next on the result. Agents commit locally and never push; the lead pushes and opens the PR from the agent's report and hand-off note.
- **Overlap gate:** before launching a wave, compare the `Files touched` of every task. Never run two tasks at once if their lists intersect. Wiring files (`main.py`, routers, `App.tsx`, `main.tsx`) and lockfiles count as files touched.
- **CI enforces three of these** (`.github/workflows/team-checks.yml`): a task branch (`Tnn-...`) may change only the files in its `docs/tasks/Tnn.yml` `files_touched` (plus `docs/tasks/Tnn.md`), and each Alembic migrations folder must have exactly one head, and a `team-sync-*` branch may change only files listed in `docs/team/SYNC_FILES` (read from the base branch). If the scope check fails, ask the architect for a spec change; never weaken the check.
- **Branch names:** every branch carries a task ID. A task branch starts with it (`T07-...`); the lead's housekeeping branches start with `spec-`, `team-sync-`, `team-`, `process-`, `closeout-` or `docs-` followed at once by a task ID (`spec-T200-foo`, `docs-T215-readme`). CI fails any other name, so a branch cannot skip the scope check by leaving out the ID. The only exceptions are prefixes listed in `docs/team/branch_exemptions` (read from the base branch, one per line); this repo's list is empty on purpose (no `dependabot/` exemption, decision on #63), while a repo that uses dependabot lists `dependabot/` there.
- **Sync PRs:** a PR that syncs team rules from the shared core comes from a `team-sync-T<nn>-...` branch. Before merging, the lead compares its diff to `docs/team/SYNC_FILES` (CI runs `sync-scope`); a file outside the list is added to the list deliberately or removed from the PR, never ignored.
- **One lead per repo:** only one lead session works on a repo at a time. Before launching a wave, list open PRs and branches (`gh pr list`, `git branch -r`) and read the open request issues; work that already exists on another branch is merged or closed first, never rebuilt.
- **Lead lock (hooks block publishing, `.claude/settings.json`):** the lock is the open issue labelled `lead-lock`, managed by `scripts/team/lead_lock.py` (`status`, `acquire --purpose "..."`, `release`). The repo is read from `LEAD_LOCK_REPO` or the git `origin` URL. At session start a hook prints who holds it. A hook blocks, unless this session holds a live lock: `git push` and `git send-pack`; `gh pr create/merge/ready`; `gh api` calls that write to `pulls`, `merges` or `git/refs` (explicit `-X POST/PUT/PATCH`, or `-f/-F/--field/--input`, which make `gh api` a POST); and GraphQL pull request and branch mutations. It is a pattern list, not a sandbox: wrapper scripts, aliases, `contents` writes and quoting tricks get past it, and `echo`/`grep` of those strings by a session without the lock is blocked by mistake. That also blocks review comments posted through `gh api .../pulls/...`. It does not cover other tools such as a GitHub MCP server, nor commits and edits in the working tree. A lock with no heartbeat for 60 minutes is stale and free. The heartbeat refreshes while the session works (each hook uses its own session's ID), and the lock is released when the session ends. If another live session holds it, tell the user which one; take over with `--force` only when the user says so. Never edit the hook or the lock issue to get around a block. If GitHub can't be reached, or the hook input has no session ID, the pre-bash hook warns and allows the command (the heartbeat and session-end hooks quietly do nothing); check `status` by hand then. `/clear` ends the session, which releases the lock; the new session must acquire it again. `acquire` reads the issue back 2 s after writing and stands down if another session wrote last; two sessions that acquire within a few seconds of each other can still both win, so run `status` before you start. Known limit: sessions in one clone (or its worktrees) share one session-id file, which `acquire` reads. The pre-bash hook binds it to the right session just before any command containing `lead_lock.py`, but a wrapper (Makefile, alias) that hides the name, or a long wait for command approval while another session starts, can bind the wrong ID. That fails safe for the session that asked (its pushes stay blocked) but can hand the lock to the other one, so check `status` after `acquire`. If the script is missing (an old branch checked out mid-session) the hooks do nothing instead of blocking every command.
- **Lead lock in CI and rollout:** the `lead-lock` job in `team-checks.yml` runs the script's offline self-test and `check-settings` (all four hooks present, as command hooks, under the right events, with `Bash` on the pre-tool hook; `disableAllHooks` fails it). `scripts/team/lead_lock.py` is synced; `.claude/settings.json` stays per repo because it may hold repo-specific permissions. **Rollout order in a repo that has neither yet:** (1) a normal task PR in that repo adds `.claude/settings.json` and the `scripts/team/lead_lock.py` line in its `docs/team/SYNC_FILES` (sync-scope reads that list from the base branch, so the script cannot ride on its own first sync); (2) then the `team-sync-` PR with the script, `team-checks.yml`, `CLAUDE.md` and `lead.md`. Until step 1 is merged, the `lead-lock` job is red there on purpose; do not make it skip a missing file.
- **Changes only from the lock holder:** any request that changes the repo (code, tests, CI, docs) is handled by the session holding the lock, even a quick fix. A session without the lock only answers questions and investigates (reads code, runs checks locally, reads CI logs) and reports what it found.
- **Wave size:** at most 3 build agents at once.
- **Migrations:** at most one migration task per wave, so there is only ever one Alembic head.
- **Dependencies:** adding a package (`uv.lock`, `package-lock.json`) is a request to the lead, applied by one agent per side at the start of the wave, not edited by parallel agents.
- **Contracts:** `docs/API.md` and `docs/DATA_MODEL.md` are frozen during a wave. Contract change requests are applied between waves, except for a Blocking defect.
- **Ports and databases:** assign each agent a port slot; the naming rules are in `docs/team/environment.md`.

## Communication
- The lead is the hub. Agents do not message each other; they put requests to other agents in their report and the lead routes them.
- **Task spec:** `architect` writes `docs/tasks/Tnn.yml` per task (owner, branch, wave, dependencies, `files_touched`, `read_first`, `ui`, acceptance IDs); the overlap gate and your prompts read it. Format in `docs/tasks/README.md`.
- **Hand-off note:** every task leaves `docs/tasks/Tnn.md`: what was built, the interface it exposes, and what the next agent needs to know. Only the task's owner writes it.
- **GitHub is the shared record** once the repo has the issue and PR templates and status labels: one issue per task (acceptance criteria, `Files touched`, dependencies), progress and hand-off as comments on it, review findings as PR line comments, defects as linked issues, questions for the user as a `needs-decision` issue. Until then, `docs/PLAN.md` and `docs/tasks/` are the record.
- **Requests become issues:** every line under `Requests:` or `Open questions:` in an agent report, and every Suggestion in a review, is turned by the lead into a GitHub issue before the session ends, labelled `task`, `needs-decision` or `deferred` (with a one-line reason for deferring). Nothing stays only in a report.
- **Review before merge:** a task PR is merged only after the reviewer the by-risk rule picks (see *Which reviewer*) returns APPROVE on its commit and CI is green. Spec PRs are read by the lead against the overlap gate before merging. The review is recorded as a comment on the PR.
- **Fix loops:** resume the same agent session rather than starting a new one, so the agent keeps its context.

## Lessons that apply to the lead
See `docs/team/lessons.md`, entries marked *lead*.
