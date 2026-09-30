# Operations

## Recommended schedule

The `agira_daily_1100` Dagster schedule runs `agira_daily_job` every calendar
day at 11:00 in `Europe/Paris`. With
the default question lag of one day, this morning run is safe. Use a scheduler
service account with read-only database access and write access limited to this
project's `data` and persistent Dagster state directories.

`agira_daily_job` publishes question and termination files to the local depots,
sends them to DARVA over SFTP, downloads DARVA results into the interrogation
depots, then archives and translates them, removing only the depot inputs whose
history artifacts were verified successfully. `agira_outbound_job` and
`agira_inbound_job` run each half on its own for manual recovery.

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

If `receive_results` fails after downloading, the file is already in
`data/depot/interrogations/{resp,rej}` and DARVA has already deleted its copy;
do not expect to download it again. Re-execute `archive_inbound_results` alone,
or launch `agira_inbound_job`. The archive step scans the depot itself and only
waits for the pull to finish, so it needs no stored output from an earlier run.

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
