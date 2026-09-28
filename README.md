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
    interrogations/
      rej/YYYY-MM-DD/{received-file.EDI, received-file.json}
      resp/YYYY-MM-DD/{received-file.EDI, received-file.json}
  depot/
    questions/RA-*.TXT
    terminations/RA-*.TXT
    interrogations/{rej,resp}/received-file.EDI
```

The history folder name is the processing date. `manifest.json` records the SQL
source date, counts, hashes, and status. An empty query creates only an `empty`
manifest: AGIRA batches require at least one item, so the pipeline never creates
an invalid empty TXT file.

## Setup and use

1. The translator lives in `agira/` (part of this repository). The local
   dependency in `pyproject.toml` points there directly. `data/` is not
   versioned: copy it over manually; the pipeline recreates missing folders.
2. Run `uv sync --extra database --extra orchestration --extra sftp`.
3. Put the PostgreSQL URL in `prd.env` as `AGIRA_DB_CONNECTION_STRING=postgresql://...`
   (or export it as an environment variable; the variable wins). `prd.env` is
   gitignored.
4. Run `uv run agira-daily all` from this directory.

Examples:

```powershell
uv run agira-daily questions --run-date 2026-09-18
uv run agira-daily terminations --run-date 2026-09-18
uv run agira-daily questions --run-date 2026-09-18 --input-json sample-rows.json
uv run agira-inbound
uv run agira-sftp sync
uv run pytest
```

`--input-json` bypasses SQL and accepts an array of query-result objects. It is
intended for mapping tests before database access is configured.

## Receiving AGIRA results

Place every file received from AGIRA in either
`data/depot/interrogations/rej/` or `data/depot/interrogations/resp/`, then run:

```powershell
uv run agira-inbound
```

The command scans both folders and uses the AGIRA reception filename plus the
decoded message family, rather than trusting the depot subfolder. A misplaced
`_REP.EDI` or `_REJ.EDI` file is therefore archived under the correct category.
The reception timestamp in the filename selects the `YYYY-MM-DD` history
folder. The original EDI file is copied unchanged and a clean UTF-8 JSON view is
written beside it. Question responses/rejections, termination rejections, and
mixed rejection files are supported.

After both history artifacts have been written successfully, the source EDI is
deleted from the depot. If the history pair already exists and is identical, it
is reported as `already_archived` and the duplicate depot source is also
deleted. A parsing failure, write failure, or different file/translation at the
same history path leaves the depot source in place and is reported as an error.

## DARVA SFTP transfer

Install with `uv sync --extra database --extra orchestration --extra sftp`.
The server (`[sftp]` in `settings.toml`) only accepts the production server's
IP. Uploads and downloads both live at the server root, and the server deletes
each file once it has been transferred.

```powershell
uv run agira-sftp pull   # server root -> data/depot/interrogations/{rej,resp}/
uv run agira-sftp push   # data/depot/{questions,terminations}/*.TXT -> server root
uv run agira-sftp sync   # pull, then push
```

`push` only sends, and then deletes, a depot file when `data/history` holds an
identical copy. `pull` writes to a hidden `.part` file before renaming it, and
leaves a file on the server if the depot already has that name. It also skips
any file we sent ourselves that the server has not consumed yet. The Dagster
outbound job pushes after publishing; the inbound job pulls before archiving.

One-time key setup: open `id_rsa_winscp.ppk` in PuTTYgen, then use
**Conversions > Export OpenSSH key** and save it as `id_rsa_darva` in the
project root. Keep the passphrase. Put the passphrase in `prd.env` as
`passphrase_for_ftp=...`. Both key files are gitignored.

## Safety and reruns

- SQL dates are bound parameters, never interpolated strings.
- JSON and TXT writes are atomic.
- Existing dated history or depot files are never overwritten. Investigate the
  prior run instead of silently replacing an auditable artifact.
- Received AGIRA files are copied byte-for-byte into dated history and their
  clean JSON translations are written atomically. A depot input is deleted only
  after both history artifacts exist and match the received content.
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

## Dagster orchestration

The Dagster code location defines two schedules. Both run every calendar day at
11:00 in the `Europe/Paris` timezone and start enabled:

- `agira_outbound_1100` runs the question and termination feeds and publishes
  their files into the local depots. The existing downstream FTP/CFT process is
  still responsible for sending those files to AGIRA.
- `agira_inbound_1100` scans both interrogation depots, writes the original and
  clean JSON into dated history, and deletes each successfully archived depot
  source.

For local development, create a persistent Dagster state directory and start
the UI plus daemon from the repository root:

```powershell
New-Item -ItemType Directory -Force .dagster | Out-Null
$env:DAGSTER_HOME = (Resolve-Path .dagster)
uv run dg dev
```

The UI is available at `http://localhost:3000`. `dg dev` must remain running for
the schedules to fire and is intended for development. For unattended
production scheduling, run the Dagster webserver and daemon as supervised
services with a persistent `DAGSTER_HOME`, the repository as working directory,
and the same database/data-directory permissions described above.

Set `AGIRA_SETTINGS_PATH` before starting Dagster only when the settings file is
not `settings.toml` in the repository root.
