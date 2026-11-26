# Shipyard-only rules

Rules that apply in this repo only and override the synced team files (`docs/team/lead.md`, `CLAUDE.md`). This
file is not in `docs/team/SYNC_FILES`, so a team sync never changes it. Each rule names the user decision behind it.

## Fix rounds (Q-05, issue #27)

User decision (Nir, 2026-11-26):

> #27 Q-05: after 2 fix rounds with Blocking items still open, stop and report (Shipyard-only rule).

This replaces "one fix round" in `docs/team/lead.md` § "Workflow" step 5 and § "Lead-only rules" for Shipyard:

- A review may get up to two fix rounds. Each round: the owning agent fixes the Blocking items, then the reviewer
  verifies only those items on the new commit.
- If Blocking items are still open after the second fix round, the lead stops work on that task and reports to the
  user (what is still blocking, and the options) instead of starting a third round.
- It applies to every review (code, contracts, docs), not only contract disagreements. Rounds are counted per
  review; a new user decision that changes the task's scope starts a new review.
