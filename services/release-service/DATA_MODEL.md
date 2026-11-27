# release-service data model

One SQLite database (`RELEASE_SERVICE_DATABASE_URL`, default `sqlite:///<data dir>/release_service.db`), created by
`create_all` at startup (idempotent; it never alters an existing table, `start-stack.sh` wipes the slot's data dir).
Tables are in `app/repos/tables.py`; all SQL is in `app/repos/releases.py`.

## `releases`
| column | type | null | meaning |
| --- | --- | --- | --- |
| `release_id` | VARCHAR(36), primary key | no | UUID string, assigned by the service |
| `artifact_name` | VARCHAR(100) | no | artifact name (events.yml ArtifactName); not checked against artifact-store (Q-16) |
| `artifact_version` | BIGINT (SQLAlchemy `BigInteger`) | no | artifact version, 1 to 2^63-1: the contract caps it (Q-40), so it fits a 64-bit integer; larger values are 422 before anything is stored |
| `status` | VARCHAR(16) | no | `pending`, `approved` or `rejected`; a decision is final (Q-10) |
| `requested_by` | TEXT | no | free non-empty string as sent (Q-30) |
| `requested_at` | VARCHAR(30) | no | UTC RFC 3339 with `Z`, set by the server |
| `decided_by` | TEXT | yes | as sent with the decision; null while pending |
| `decided_at` | VARCHAR(30) | yes | set by the server with the decision |
| `promoted_at` | VARCHAR(30) | yes | time of the first promote (Q-31); only an approved release can be promoted (Q-16) |

No other index: every query is by primary key. No foreign keys.

## Transactions
Each repo method is one transaction that commits before the route returns. On SQLite every transaction starts with
`BEGIN IMMEDIATE` (set in `app/repos/engine.py`), with a 60 s busy timeout and WAL for file databases, so the
read-then-write of decide and promote is serialised: concurrent decisions have exactly one winner, concurrent
promotes all return the first `promoted_at`.

## State changes
- request: insert with status `pending`, the three later fields null.
- decide: only when `status = pending`; sets status, `decided_by`, `decided_at`; otherwise 409 release_already_decided.
- promote: only when `status = approved`; sets `promoted_at` if null; otherwise 409 release_not_approved.
