# Operations

## Recommended schedule

The Dagster schedules run every calendar day at 11:00 in `Europe/Paris`. With
the default question lag of one day, this morning run is safe. Use a scheduler
service account with read-only database access and write access limited to this
project's `data` and persistent Dagster state directories.

`agira_outbound_1100` publishes question and termination files to the local
depots; the downstream FTP/CFT service remains responsible for network transfer.
`agira_inbound_1100` archives and translates received files, then removes only
the depot inputs whose history artifacts were verified successfully.

The job returns exit code `0` on a published or explicitly empty feed and `2` on
configuration, extraction, validation, or publication failure. Capture stdout,
stderr, and exit code in the scheduler.

## Success criteria

For each feed and processing date, require exactly one history directory with a
manifest. `status = published` requires matching JSON/TXT hashes and a same-name
TXT in the corresponding depot. `status = empty` is a valid technical result but
may warrant a business alert.

## Recovery

The pipeline refuses overwrite. For a failed partial run, inspect the manifest
and hashes first. If no downstream transfer occurred, move the exact dated
history directory and depot file to a controlled quarantine location, record the
reason, and rerun. Do not delete or replace production artifacts without an
audit trail.

If questions succeed and terminations fail (or the reverse), rerun only the
failed feed. The independent daily folders are intentional.

## Monitoring checklist

- scheduler exit code;
- missing daily manifest by the agreed cutoff;
- unexpectedly empty or unusually large row/item counts;
- history JSON/TXT hash mismatch;
- depot file not consumed within the FTP service-level objective;
- database/query failures and model validation failures;
- AGIRA rejection files, correlated to the original history manifest.

## Data protection

History contains names, addresses, birth dates, licence data, and contract data.
Use least-privilege access, encrypted disks/backups, a documented retention
period, and audited deletion. Never write the database connection string or raw
rows to logs.
