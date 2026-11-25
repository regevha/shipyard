# User brief (wave 1)

**Source:** the user's first message to the lead session, sent 2026-11-25 20:50 Asia/Jerusalem (UTC+02:00), in the
Claude session https://claude.ai/code/session_01V8xnBwGmVDiRfCmu4EZrSn. It was not taken from a file or from memory.
Stored by the lead on the user's request of 2026-11-25 21:12 (task T013, issue #38).

Everything between the two rules below is the message verbatim, unedited (only the surrounding Markdown quote
fence is added). Anything elsewhere in the repo that says "the brief" or "the user brief" must be traceable to a
sentence here; if it is not, it is the lead's or an agent's assumption and is labelled as such in
`docs/OPEN_QUESTIONS.md`.

---

```text
You are the lead for a new project, Shipyard (repo regevha/shipyard): a build and release platform made of four services. Wave 1 is CONTRACTS ONLY. Write no service code.

The four services (Python with FastAPI, one stack for all):
1. Pipeline runner: runs a pipeline definition step by step and reports each step and the final result.
2. Artifact store: accepts uploads from the runner, stores them with a version and checksum, serves them back.
3. Release approval service: holds a release request, records an approve or reject decision with who and when, blocks promotion until approved.
4. Monitoring dashboard: receives events from the other three and shows builds, artifacts, approvals and failures. It also serves a small web frontend, so there is no fifth service. The frontend is plain HTML pages with a little JavaScript to refresh the data, with no build step and no React for now; a React app can be considered in wave 3 if the dashboard needs it.

Services talk over plain HTTP for now. The dashboard exposes an events endpoint that the others post to. A real event queue is a later wave.

Before starting wave 1, verify the models: confirm that this lead session is running on the Opus model, and open the agent definition files and confirm that the architect and the reviewer are both set to use Opus. If any of the three is not, stop and report it to me before doing anything else; do not change it yourself.

Wave 1 deliverables, as files in the repo:
- docs/PLAN.md with the three waves and a task table (ID, task, acceptance criterion that can actually be run, files touched, status).
- contracts/events.yml: build started, build finished (passed or failed), artifact uploaded, release requested, release approved or rejected. Each event has fields, types and an example.
- contracts/api-*.yml: one file per service with endpoints, request and response shapes.
- contracts/errors.yml: one shared error envelope and the status codes, agreed once.
- docs/OPEN_QUESTIONS.md: every conflict or unclear point. Report conflicts; never silently pick a side.

Team roles and rules:
- Architect writes the specs. Reviewer checks that the four services' contracts agree with each other, using the full reviewer because this is a contracts change. The reviewer comes before merge, not after.
- Only one lead session works on this repo at a time. Before starting, check for open PRs and issues.
- Every request or finding in an agent report becomes a GitHub issue labelled todo, deferred or needs-decision. Every reviewer finding, such as two contracts that disagree, becomes its own issue naming the two files and the exact fields in conflict. The architect's fix task spec links to that issue. A choice that needs me is labelled needs-decision; do not guess it.
- Fix rounds are limited: if the reviewer and architect go around more than twice and the contracts still disagree, stop and report to me instead of looping. Do not merge anything while a conflict is open, and do not start wave 2 on contracts that still disagree.
- Branch names carry the task ID. Merge one PR at a time and check that CI on main is green after each.
- Acceptance criteria must be run. Anything that cannot be run is marked unverified, not done.
- Each report ends with an Evidence line: commit hash, files changed, checks run, and whether the aggregate CI check was green on the head commit.
- Set up CI from day one: a required aggregate check, a parse check that every contract and task spec is valid YAML, and a check that every example in the contracts validates against its schema.

Stop at the end of wave 1. Report what is done, what is unverified, and what needs my decision. Do not start wave 2.
```

---

## What the lead passed to agents, and what is not in the text above

The architect (T010) did not see this text; it got the lead's prompt, which restated the brief and added the lead's
own constraints. These items in `docs/PLAN.md` and `docs/OPEN_QUESTIONS.md` come from the lead, not from the text
above, and are tracked as assumptions:

- CI tasks are part of wave 1 (the text says "Wave 1 is CONTRACTS ONLY" and, separately, "Set up CI from day one"): Q-25.
- `api-*.yml` as OpenAPI 3.1.0 and `events.yml`/`errors.yml` as JSON Schema 2020-12, and the rest of
  `docs/PLAN.md` § "Contract file format": Q-26.
- What waves 2 and 3 contain beyond the two sentences above that name a later wave (the event queue "is a later
  wave"; React "can be considered in wave 3"): Q-27.
- "Two fix rounds": the text says "go around more than twice and the contracts still disagree": Q-05.
- "Acceptance commands": the text says "acceptance criterion that can actually be run": Q-08, Q-24.
