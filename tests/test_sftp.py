import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from agira_daily.sftp import pull, push


class FakeDarva:
    """Server root that consumes uploads and deletes files once downloaded."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = dict(files)
        self.uploaded: dict[str, bytes] = {}

    def putfo(self, stream, name, confirm=True):
        assert confirm is False
        self.uploaded[name] = stream.read()

    def listdir_attr(self, path):
        entries = [SimpleNamespace(filename="subdir", st_mode=stat.S_IFDIR)]
        return entries + [
            SimpleNamespace(filename=name, st_mode=stat.S_IFREG) for name in self.files
        ]

    def get(self, name, local):
        Path(local).write_bytes(self.files.pop(name))

    def remove(self, name):
        if name not in self.files:
            raise FileNotFoundError(name)
        del self.files[name]


def _write(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_push_sends_archived_depot_files_and_clears_depot(tmp_path: Path) -> None:
    depot, history = tmp_path / "depot", tmp_path / "history"
    name = "RA-AC000189-HOCSFR42.AC000189_202609280002.TXT"
    _write(history / "terminations/2026-09-28" / name, b"payload")
    source = _write(depot / "terminations" / name, b"payload")
    _write(depot / "questions/.gitkeep", b"")
    server = FakeDarva({})

    assert push(server, depot=depot, history=history) == [name]
    assert server.uploaded == {name: b"payload"}
    assert not source.exists()
    assert (history / "terminations/2026-09-28" / name).exists()


def test_push_refuses_file_without_identical_history_copy(tmp_path: Path) -> None:
    depot, history = tmp_path / "depot", tmp_path / "history"
    name = "RA-AC000189-X.TXT"
    _write(history / "questions/2026-09-28" / name, b"other")
    source = _write(depot / "questions" / name, b"payload")
    server = FakeDarva({})

    with pytest.raises(FileNotFoundError):
        push(server, depot=depot, history=history)
    assert server.uploaded == {}
    assert source.exists()


def test_pull_sorts_files_into_inbound_depot(tmp_path: Path) -> None:
    depot, history = tmp_path / "depot", tmp_path / "history"
    ours = "RA-AC000189-HOCSFR42.AC000189_202609280002.TXT"
    _write(history / "terminations/2026-09-28" / ours, b"sent")
    server = FakeDarva(
        {
            "AC000189_20260928120000_REJ.EDI": b"rej",
            "AC000189_20260928120000_REP.EDI": b"rep",
            ours: b"sent",
        }
    )

    received = pull(server, depot=depot, history=history)

    assert received == [
        "AC000189_20260928120000_REJ.EDI",
        "AC000189_20260928120000_REP.EDI",
    ]
    inbound = depot / "interrogations"
    assert (inbound / "rej/AC000189_20260928120000_REJ.EDI").read_bytes() == b"rej"
    assert (inbound / "resp/AC000189_20260928120000_REP.EDI").read_bytes() == b"rep"
    assert server.files == {ours: b"sent"}
    assert not list(inbound.rglob(".*.part"))


def test_pull_leaves_remote_file_when_depot_copy_exists(tmp_path: Path) -> None:
    depot, history = tmp_path / "depot", tmp_path / "history"
    name = "AC000189_20260928120000_REP.EDI"
    _write(depot / "interrogations/resp" / name, b"earlier")
    server = FakeDarva({name: b"new"})

    with pytest.raises(FileExistsError):
        pull(server, depot=depot, history=history)
    assert server.files == {name: b"new"}
