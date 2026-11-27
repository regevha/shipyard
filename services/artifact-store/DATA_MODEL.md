# artifact-store data model

Internal to the service (not a contract). SQLite for now (`ARTIFACT_STORE_DATABASE_URL`), tables created at
startup with `metadata.create_all` (no migrations in wave 2). All SQL lives in `app/repos/artifacts.py`.

## Table `artifacts`

One row per uploaded version. Rows are never updated or deleted.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `VARCHAR(36)` PK | UUID generated in Python |
| `name` | `VARCHAR(100)` NOT NULL | artifact name, Q-29 rule, case-sensitive |
| `version` | `INTEGER` NOT NULL | per name, starts at 1 (Q-17): the next one is `max(version) + 1`; capped at 2^63-1 (Q-40): when `max(version)` is already 2^63-1 nothing is stored (no blob, no row, no event) and the upload answers 500 |
| `checksum` | `VARCHAR(64)` NOT NULL | SHA-256 of the bytes, lowercase hex |
| `size_bytes` | `INTEGER` NOT NULL | 0 to 104857600 |
| `build_id` | `VARCHAR(36)` NOT NULL | recorded as sent, not checked with pipeline-runner |
| `uploaded_at` | `DATETIME` NOT NULL | UTC, whole seconds (answered as `...Z`) |
| `blob_path` | `VARCHAR(255)` NOT NULL | file name under the blob directory |

Constraint `uq_artifacts_name_version` UNIQUE (`name`, `version`); its index serves the download lookup and
the `max(version)` query. Two concurrent uploads of one name that pick the same version: the second commit
fails on the constraint and is retried with the next version (up to 10 times).

## Blob files

`$SHIPYARD_DATA_DIR/artifact_store_blobs/<blob_path>` (data dir default `/tmp/shipyard/slot<SHIPYARD_SLOT>`),
written by `app/repos/blobs.py` through a `.part` file, fsynced and renamed, before the row is committed. If the
commit fails the file is removed. A crash between the two can leave an orphan file; no row points to it.
