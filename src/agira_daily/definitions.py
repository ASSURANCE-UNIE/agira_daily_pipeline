import os
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import dagster as dg
from agira_api.parser import ParseError
from dagster import OpExecutionContext

from .config import PipelineConfig
from .inbound import archive_inbound_file, discover_inbound_files
from .runner import Feed, run_feed
from .sftp import connect, pull, push


SCHEDULE_CRON = "0 11 * * *"
DEFAULT_SETTINGS_PATH = Path("settings.toml")


def _settings_path() -> Path:
    configured = os.getenv("AGIRA_SETTINGS_PATH")
    return Path(configured).resolve() if configured else DEFAULT_SETTINGS_PATH.resolve()


def _load_config() -> PipelineConfig:
    return PipelineConfig.load(_settings_path())


@contextmanager
def _sftp_session() -> Iterator[Any]:
    with connect(_settings_path()) as client, client.open_sftp() as sftp:
        yield sftp


def _publication_result(
    feed: Feed,
    run_date: date,
    context: OpExecutionContext,
) -> dict[str, str | None]:
    publication = run_feed(
        feed,
        config=_load_config(),
        run_date=run_date,
    )
    metadata: dict[str, Any] = {
        "feed": publication.feed,
        "status": publication.status,
        "run_date": publication.run_date.isoformat(),
        "source_date": publication.source_date.isoformat(),
        "history_dir": dg.MetadataValue.path(str(publication.history_dir)),
    }
    if publication.depot_path is not None:
        metadata["depot_path"] = dg.MetadataValue.path(str(publication.depot_path))
    context.add_output_metadata(metadata)
    context.log.info(
        "%s %s for %s: %s",
        publication.feed,
        publication.status,
        publication.run_date,
        publication.depot_path or publication.history_dir,
    )
    return {
        "feed": publication.feed,
        "status": publication.status,
        "run_date": publication.run_date.isoformat(),
        "history_dir": str(publication.history_dir),
        "depot_path": (
            str(publication.depot_path)
            if publication.depot_path is not None
            else None
        ),
    }


@dg.op
def processing_date(context: OpExecutionContext) -> str:
    config = _load_config()
    run_date = datetime.now(ZoneInfo(config.timezone)).date()
    context.log.info("AGIRA processing date: %s (%s)", run_date, config.timezone)
    return run_date.isoformat()


@dg.op
def publish_questions(
    context: OpExecutionContext,
    run_date: str,
) -> dict[str, str | None]:
    return _publication_result("questions", date.fromisoformat(run_date), context)


@dg.op
def publish_terminations(
    context: OpExecutionContext,
    run_date: str,
) -> dict[str, str | None]:
    return _publication_result("terminations", date.fromisoformat(run_date), context)


@dg.op
def send_depot_files(
    context: OpExecutionContext,
    questions: dict[str, str | None],
    terminations: dict[str, str | None],
) -> list[str]:
    config = _load_config()
    with _sftp_session() as sftp:
        sent = push(sftp, depot=config.depot, history=config.history)
    context.log.info("Sent %d file(s) to DARVA: %s", len(sent), ", ".join(sent))
    return sent


@dg.op
def receive_results(context: OpExecutionContext) -> list[str]:
    config = _load_config()
    with _sftp_session() as sftp:
        received = pull(sftp, depot=config.depot, history=config.history)
    context.log.info("Received %d file(s) from DARVA: %s", len(received), ", ".join(received))
    return received


@dg.op
def archive_inbound_results(
    context: OpExecutionContext,
    received: list[str],
) -> dict[str, int]:
    config = _load_config()
    sources = discover_inbound_files(config.depot)
    counts: Counter[str] = Counter()
    failures: list[tuple[Path, Exception]] = []

    for source in sources:
        try:
            result = archive_inbound_file(source, history_root=config.history)
        except (OSError, UnicodeError, ParseError, ValueError) as exc:
            failures.append((source, exc))
            context.log.error("Failed to archive %s: %s", source.name, exc)
            continue
        counts[result.status] += 1
        counts[result.category] += 1
        context.log.info(
            "%s %s file %s to %s and removed the depot source",
            result.status,
            result.category,
            result.source_path.name,
            result.history_dir,
        )

    summary = {
        "discovered": len(sources),
        "archived": counts["archived"],
        "already_archived": counts["already_archived"],
        "responses": counts["resp"],
        "rejections": counts["rej"],
        "failed": len(failures),
    }
    context.add_output_metadata(summary)
    if failures:
        failed_names = ", ".join(source.name for source, _ in failures)
        raise dg.Failure(
            description=(
                f"{len(failures)} AGIRA inbound file(s) failed and remain in depot: "
                f"{failed_names}"
            )
        )
    if not sources:
        context.log.info("No AGIRA inbound files found")
    return summary


@dg.job(description="Publish daily AGIRA question and termination files and send them to DARVA.")
def agira_outbound_job() -> None:
    run_date = processing_date()
    send_depot_files(publish_questions(run_date), publish_terminations(run_date))


@dg.job(description="Fetch AGIRA results from DARVA, then translate and archive them.")
def agira_inbound_job() -> None:
    archive_inbound_results(receive_results())


SCHEDULE_TIMEZONE = _load_config().timezone

agira_outbound_1100 = dg.ScheduleDefinition(
    name="agira_outbound_1100",
    job=agira_outbound_job,
    cron_schedule=SCHEDULE_CRON,
    execution_timezone=SCHEDULE_TIMEZONE,
    default_status=dg.DefaultScheduleStatus.RUNNING,
    description=(
        "At 11:00 local time, build question and termination files in the depots."
    ),
)

agira_inbound_1100 = dg.ScheduleDefinition(
    name="agira_inbound_1100",
    job=agira_inbound_job,
    cron_schedule=SCHEDULE_CRON,
    execution_timezone=SCHEDULE_TIMEZONE,
    default_status=dg.DefaultScheduleStatus.RUNNING,
    description=(
        "At 11:00 local time, translate received files, archive them, and clear "
        "successfully processed depot inputs."
    ),
)

defs = dg.Definitions(
    jobs=[agira_outbound_job, agira_inbound_job],
    schedules=[agira_outbound_1100, agira_inbound_1100],
)
