# Lessons from the dry runs

Each lesson names the roles it applies to. Read only the entries for your role. Role-specific review lessons also live in each agent's own file under "Rules learned from review".

- **Parallel work** (*lead, project-manager*): never run two agents at once that edit files the other one tests or builds on. Sequence them, or give each its own checkout.
- **Real browser for UI** (*reviewer, tester, e2e-tester, ux-reviewer*, UI tasks only): from the first UI task on, check in a real browser (Playwright with system Chrome), not only in jsdom. jsdom cannot see layout, real focus, native dialogs or contrast. Run a short browser smoke test as an in-review gate for each UI task, before the full e2e wave. The smoke test must run against the real backend: in the Task Manager dry run a stub-server smoke missed a double-submit bug and a long-title layout bug that the real app showed.
- **Tests are not screens** (*lead, reviewer, ux-reviewer*, UI tasks only): "tests pass" is not evidence that the screen is right. Closing a UI task needs a reviewer or ux-reviewer who looked at the running app.
- **Document conflicts** (*all*): `docs/PRODUCT.md` wins over the contracts, the contracts over `docs/DESIGN.md`, and that over `docs/PLAN*.md`. Report a conflict to the lead; never silently pick one. (Also in `CLAUDE.md`.)
- **Plan health** (*lead, project-manager*): run the plan-health check (file overlaps, missing dependencies, contradictions between docs, duplicate task IDs) before launching each wave.
- **Task IDs** (*architect, project-manager*): task IDs are unique across plan files; add rows only after re-reading the file, and edit only your own row.
- **Stopped agents** (*lead*): agents that are stopped mid-task leave unfinished files; treat those as unfinished and redo them, never as partial credit.
