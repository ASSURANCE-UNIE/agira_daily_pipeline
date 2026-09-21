# AGIRA daily pipeline

This project owns the operational workflow around the separate
`agira-ra-translator` package. It executes the supplied SQL, builds validated
business JSON, renders AGIRA files, archives both artifacts, and publishes the
TXT files to local depot folders. FTP transfer remains the responsibility of the
existing downstream process.

## Daily behavior

For a processing date `D`:

- terminations select records dated `D - 35 calendar days`;
- questions select new business dated `D - 1 calendar day` by default;
- set `question_lag_days = 0` only when the job runs after the business day has
  closed and late transactions cannot still arrive;
- one question file and one termination file are published on a normal day—two
  TXT files total, each in its own depot.

Runtime layout:

```text
data/
  history/
    questions/YYYY-MM-DD/{questions.json, RA-*.TXT, manifest.json}
    terminations/YYYY-MM-DD/{terminations.json, RA-*.TXT, manifest.json}
  depot/
    questions/RA-*.TXT
    terminations/RA-*.TXT
```

The history folder name is the processing date. `manifest.json` records the SQL
source date, counts, hashes, and status. An empty query creates only an `empty`
manifest: AGIRA batches require at least one item, so the pipeline never creates
an invalid empty TXT file.

## Setup and use

1. Keep the translator in the nested `agira/` repository. The local dependency
   in `pyproject.toml` points there directly.
2. Run `uv sync --extra database`.
3. Copy each `query.sql.example` to `query.sql` in `queries/questions` and
   `queries/terminations`, then replace the placeholder SQL.
4. Put the ODBC connection string in `AGIRA_DB_CONNECTION_STRING`.
5. Run `uv run agira-daily all` from this directory.

Examples:

```powershell
uv run agira-daily questions --run-date 2026-09-18
uv run agira-daily terminations --run-date 2026-09-18
uv run agira-daily questions --run-date 2026-09-18 --input-json sample-rows.json
uv run pytest
```

`--input-json` bypasses SQL and accepts an array of query-result objects. It is
intended for mapping tests before database access is configured.

## Safety and reruns

- SQL dates are bound parameters, never interpolated strings.
- JSON and TXT writes are atomic.
- Existing dated history or depot files are never overwritten. Investigate the
  prior run instead of silently replacing an auditable artifact.
- Question sequence `0001` and termination sequence `0002` are deliberately
  different to prevent filename collisions if both depots later share one FTP
  landing directory.
- Database credentials stay in environment variables; query files and runtime
  data are ignored where appropriate.

## Decisions still requiring confirmation

Before production scheduling, confirm these points with AGIRA/data owners:

1. whether “35 days” means calendar days or business days, and which date/time
   field is authoritative;
2. whether the question cutoff may use same-day data (`lag = 0`) and how late
   transactions are handled;
3. the exact termination SQL shape. The current `record_json` boundary avoids
   inventing joins before the source schema is known;
4. what the FTP process does after transfer (move, delete, or receipt marker),
   plus retry and duplicate rules;
5. the sequence allocation and AGIRA account/application codes in
   `settings.toml`;
6. retention, encryption, and access controls for personal data in history;
7. whether a zero-row day needs an external operational alert despite producing
   no AGIRA file.

See `docs/OPERATIONS.md` for scheduling, monitoring, and recovery guidance.
