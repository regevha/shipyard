# pipeline-runner data model

SQLite for now (`PIPELINE_RUNNER_DATABASE_URL`, default `sqlite:///<data dir>/pipeline_runner.db`). Tables are
created at startup with `metadata.create_all` (no migrations in wave 2; the data is disposable). All SQL is in
`app/repos/`. Timestamps are stored as UTC strings like `2026-11-25T10:00:00.123Z` (the contract's
`Timestamp`), so they round-trip unchanged on any database.

## runs (one row per run = one build)
| column | type | notes |
| --- | --- | --- |
| build_id | VARCHAR(36) PK | UUID string generated in Python (Q-28) |
| pipeline_name | VARCHAR(100) | validated by the PipelineName rule (#119) |
| status | VARCHAR(16) | `running`, `passed`, `failed` |
| created_at | VARCHAR(30) | when the run was accepted |
| finished_at | VARCHAR(30) NULL | null while running |
| failed_step | VARCHAR NULL | name of the failed step; null unless a step failed |
| failure_reason | VARCHAR(64) NULL | `artifact upload failed` or null |

## run_steps (the definition's steps, in order)
| column | type | notes |
| --- | --- | --- |
| build_id | VARCHAR(36) PK, FK runs.build_id (ON DELETE CASCADE) | |
| position | INTEGER PK | 0-based index in the definition |
| name | VARCHAR | unique within a run (checked at request validation) |
| command | VARCHAR | recorded, never executed (Q-19) |
| status | VARCHAR(16) | `pending`, `running`, `passed`, `failed`, `skipped` |
| started_at | VARCHAR(30) NULL | |
| finished_at | VARCHAR(30) NULL | |

The primary keys give the only lookups the service does (by `build_id`, steps ordered by `position`).
