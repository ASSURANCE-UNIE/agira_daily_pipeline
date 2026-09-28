from __future__ import annotations

import base64
import io
import stat
import tomllib
from pathlib import Path
from typing import Any

from .db import connection_string
from .inbound import _REJECTION_NAME


OUTBOUND_FEEDS = ("questions", "terminations")


def connect(settings_path: Path) -> Any:
    """Open the DARVA SFTP session; the caller closes the returned SSHClient."""

    try:
        import paramiko
    except ImportError as exc:
        raise RuntimeError(
            "SFTP support is not installed; run `uv sync --extra sftp`"
        ) from exc
    settings_path = settings_path.resolve()
    root = settings_path.parent
    with settings_path.open("rb") as stream:
        settings = tomllib.load(stream)["sftp"]
    host, port = str(settings["host"]), int(settings["port"])
    key_type, key_data = str(settings["host_key"]).split()
    client = paramiko.SSHClient()
    # Pinned host key; SSHClient's default RejectPolicy refuses anything else.
    client.get_host_keys().add(
        f"[{host}]:{port}",
        key_type,
        paramiko.RSAKey(data=base64.b64decode(key_data)),
    )
    client.connect(
        host,
        port=port,
        username=str(settings["username"]),
        key_filename=str(root / settings["private_key"]),
        passphrase=connection_string(str(settings["passphrase_env"]), root / "prd.env"),
        look_for_keys=False,
        allow_agent=False,
        timeout=30,
    )
    return client


def _sent_before(history: Path, name: str) -> list[Path]:
    return [
        path
        for feed in OUTBOUND_FEEDS
        for path in (history / feed).glob(f"*/{name}")
    ]


def push(sftp: Any, *, depot: Path, history: Path) -> list[str]:
    """Upload depot TXT files to the server root, then delete them locally.

    A file is only sent (and deleted) when history holds an identical copy.
    """

    sent: list[str] = []
    for feed in OUTBOUND_FEEDS:
        for path in sorted((depot / feed).glob("*.TXT")):
            payload = path.read_bytes()
            if not any(copy.read_bytes() == payload for copy in _sent_before(history, path.name)):
                raise FileNotFoundError(
                    f"{path.name} has no identical copy in history; not sending it"
                )
            # The server consumes uploads immediately, so confirm=False skips the
            # post-upload stat that would fail on the vanished file.
            sftp.putfo(io.BytesIO(payload), path.name, confirm=False)
            path.unlink()
            sent.append(path.name)
    return sent


def pull(sftp: Any, *, depot: Path, history: Path) -> list[str]:
    """Download every file at the server root into the inbound depot folders."""

    received: list[str] = []
    for entry in sorted(sftp.listdir_attr("."), key=lambda item: item.filename):
        name = entry.filename
        if not stat.S_ISREG(entry.st_mode or 0) or _sent_before(history, name):
            continue  # skip folders and our own uploads the server has not consumed yet
        category = "rej" if _REJECTION_NAME.search(name) or "CSHRFR" in name.upper() else "resp"
        target = depot / "interrogations" / category / name
        if target.exists():
            raise FileExistsError(f"{target} already exists; {name} left on the server")
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(f".{name}.part")  # dotfiles are ignored by agira-inbound
        sftp.get(name, str(partial))
        partial.replace(target)
        try:
            sftp.remove(name)
        except FileNotFoundError:
            pass  # the server already deleted it on download
        received.append(name)
    return received


def main() -> None:
    import argparse
    import sys

    from .config import PipelineConfig

    parser = argparse.ArgumentParser(
        prog="agira-sftp",
        description="Send depot files to DARVA and fetch AGIRA results.",
    )
    parser.add_argument("direction", choices=("pull", "push", "sync"))
    parser.add_argument("--settings", type=Path, default=Path("settings.toml"))
    arguments = parser.parse_args()
    try:
        config = PipelineConfig.load(arguments.settings)
        with connect(arguments.settings) as client, client.open_sftp() as sftp:
            paths = {"depot": config.depot, "history": config.history}
            # sync pulls first so nothing we upload can be mistaken for a reply.
            if arguments.direction in ("pull", "sync"):
                for name in pull(sftp, **paths):
                    print(f"received: {name}")
            if arguments.direction in ("push", "sync"):
                for name in push(sftp, **paths):
                    print(f"sent: {name}")
    except Exception as exc:  # network, auth, and file errors all mean a failed run
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
