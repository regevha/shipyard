# Dashboard data model

Documentation, not a contract (wave 2: SQLite, `metadata.create_all` at startup, no migrations). URL in
`DASHBOARD_DATABASE_URL`, default `sqlite:///$SHIPYARD_DATA_DIR/dashboard.db`. All SQL is in `app/repos/`.

## Tables (`app/repos/tables.py`)

| Table | Key | Columns | Index |
| --- | --- | --- | --- |
| `events` | `event_id` | `type`, `occurred_at` (UTC datetime), `body` (JSON, the accepted event) | |
| `builds` | `build_id` | `pipeline_name`, `started_at`, `finished_at` (original timestamp strings, null until the event arrives), `outcome` (`passed`/`failed`, null = running), `failed_step`, `failure_reason`, `steps` (JSON list, `[]` until build.finished), `last_event_at` (UTC datetime) | `last_event_at`, `outcome` |
| `artifacts` | (`name`, `version`) | `checksum`, `size_bytes`, `build_id`, `uploaded_at` (string), `uploaded_ts` (UTC datetime) | `uploaded_ts` |
| `releases` | `release_id` | `artifact_name`, `artifact_version`, `requested_by`, `requested_at`, `decision`, `decided_by`, `decided_at`, `last_event_at` | `last_event_at` |

## How a view is derived from events

`POST /events` stores the event in `events` and folds it into one view row, in one transaction that is
committed before the 202 is sent (so the next read sees it). One writer at a time (a lock in
`app/repos/events.py`), because the fold is read-modify-write.

- Duplicate `event_id`: 202, nothing changes (first accepted body wins, Q-11).
- `build.started` sets `started_at`; `build.finished` sets `finished_at`, `outcome`, `failed_step`,
  `failure_reason`, `steps`. A field already set is not overwritten (first accepted wins, also for a second
  event of the same type with a different `event_id`). The row is created by whichever event arrives first, so
  `build.finished` before `build.started` still gives one build. `pipeline_name` comes from the first event.
- Build `status`: `running` while `outcome` is null (only build.started arrived), else the outcome.
- `artifact.uploaded`: one row per (name, version), first wins. Every uploaded artifact is listed, also one
  whose build failed (#131 option a); there is no join with `builds`.
- `release.requested` sets `requested_by`/`requested_at`; `release.decided` sets `decision`, `decided_by`,
  `decided_at`. `artifact` comes from whichever event arrived first. Status: `pending` while `decision` is
  null, else the decision. No promotion column (Q-14, Q-31).
- Missing fields are null (lists `[]`) in the response, never absent.

## Ordering

Newest first. Builds and releases: `last_event_at` descending, the maximum `occurred_at` over all events
received for the item (a late-arriving older event never moves an item). Artifacts: `uploaded_ts` descending.
Ties break by key ascending, so pages are stable. `limit` 1-200 (default 50), `offset` >= 0.
`occurred_at` is compared as an instant (fractional seconds allowed), not as a string.
