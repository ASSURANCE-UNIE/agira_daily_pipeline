# TODO

## DARVA SFTP go-live (production server)

The SFTP code (`agira-sftp`, `src/agira_daily/sftp.py`) is tested against a fake
server only; DARVA accepts connections from the production server's IP alone.

- [ ] Rotate the SFTP key passphrase (it was exposed in a chat transcript), or ask
      DARVA for a new key, then update `passphrase_for_ftp` in `prd.env`.
- [ ] Install on the Windows server: `winget install astral-sh.uv`, clone, then
      `uv sync --extra database --extra orchestration --extra sftp`.
      Use uv, not Docker (Docker Desktop isn't supported on Windows Server).
- [ ] Convert the key: PuTTYgen > load `id_rsa_winscp.ppk` > Conversions >
      Export OpenSSH key (keep the passphrase) > save as `id_rsa_darva` in the
      project root.
- [ ] Copy `prd.env` to the server (`AGIRA_DB_CONNECTION_STRING`, `passphrase_for_ftp`).
- [ ] First live test: `uv run agira-sftp pull` (safest; downloads whatever is
      waiting). If login is rejected, the server likely only accepts SHA-1
      `ssh-rsa` signatures: pass
      `disabled_algorithms={"pubkeys": ["rsa-sha2-256", "rsa-sha2-512"]}` to
      `client.connect` in `sftp.py`.
- [ ] Then `uv run agira-sftp push` and confirm DARVA received the file.
- [ ] Run the Dagster daemon as a supervised service (or schedule
      `agira-daily all` + `agira-sftp sync` in Task Scheduler).

Known limit: `pull` sorts downloads into `rej/` or `resp/` by filename only
(`REJ` / `CSHRFR` means rejection, anything else goes to response).
`agira-inbound` re-classifies by filename and content anyway.
