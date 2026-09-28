from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from dagster import DefaultScheduleStatus

from agira_daily import definitions
from agira_daily.publishing import Publication


class EmptyServer:
    def listdir_attr(self, path):
        return []


def _fake_sftp(monkeypatch) -> None:
    @contextmanager
    def session():
        yield EmptyServer()

    monkeypatch.setattr(definitions, "_sftp_session", session)


def test_dagster_schedules_run_daily_at_1100_paris() -> None:
    schedules = {
        definitions.agira_outbound_1100,
        definitions.agira_inbound_1100,
    }

    assert {schedule.cron_schedule for schedule in schedules} == {"0 11 * * *"}
    assert {schedule.execution_timezone for schedule in schedules} == {
        "Europe/Paris"
    }
    assert {schedule.default_status for schedule in schedules} == {
        DefaultScheduleStatus.RUNNING
    }


def test_inbound_job_succeeds_when_depot_is_empty(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = SimpleNamespace(
        depot=tmp_path / "data/depot",
        history=tmp_path / "data/history",
    )
    monkeypatch.setattr(definitions, "_load_config", lambda: config)
    _fake_sftp(monkeypatch)

    result = definitions.agira_inbound_job.execute_in_process()

    assert result.success
    output = result.output_for_node("archive_inbound_results")
    assert output == {
        "discovered": 0,
        "archived": 0,
        "already_archived": 0,
        "responses": 0,
        "rejections": 0,
        "failed": 0,
    }


def test_outbound_job_runs_both_feeds_for_one_processing_date(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = SimpleNamespace(
        timezone="Europe/Paris",
        depot=tmp_path / "data/depot",
        history=tmp_path / "data/history",
    )
    calls: list[tuple[str, date]] = []

    def fake_run_feed(feed, *, config, run_date):
        calls.append((feed, run_date))
        history_dir = tmp_path / "data/history" / feed / run_date.isoformat()
        return Publication(
            feed=feed,
            run_date=run_date,
            source_date=run_date,
            history_dir=history_dir,
            json_path=None,
            txt_path=None,
            depot_path=None,
            status="empty",
        )

    monkeypatch.setattr(definitions, "_load_config", lambda: config)
    monkeypatch.setattr(definitions, "run_feed", fake_run_feed)
    _fake_sftp(monkeypatch)

    result = definitions.agira_outbound_job.execute_in_process()

    assert result.success
    assert {feed for feed, _ in calls} == {"questions", "terminations"}
    assert len({run_date for _, run_date in calls}) == 1
    assert result.output_for_node("send_depot_files") == []
