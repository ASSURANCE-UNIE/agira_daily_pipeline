from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from agira_api.models import Emitter


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    root: Path
    environment: str
    account_code: str
    emitter: Emitter
    question_sequence: int
    termination_sequence: int
    timezone: str
    question_lag_days: int
    termination_lag_days: int
    connection_string_env: str
    question_query: Path
    termination_query: Path
    history: Path
    depot: Path

    @classmethod
    def load(cls, path: Path) -> "PipelineConfig":
        settings_path = path.resolve()
        root = settings_path.parent
        with settings_path.open("rb") as stream:
            data = tomllib.load(stream)
        agira = data["agira"]
        schedule = data["schedule"]
        database = data["database"]
        paths = data["paths"]
        question_sequence = int(agira["question_sequence"])
        termination_sequence = int(agira["termination_sequence"])
        if question_sequence == termination_sequence:
            raise ValueError(
                "question_sequence and termination_sequence must differ to avoid "
                "same-day AGIRA filename collisions"
            )
        return cls(
            root=root,
            environment=str(agira["environment"]),
            account_code=str(agira["account_code"]),
            emitter=Emitter(
                country_code=str(agira["country_code"]),
                company_code=str(agira["company_code"]),
                internal_company_code=str(agira["internal_company_code"]),
            ),
            question_sequence=question_sequence,
            termination_sequence=termination_sequence,
            timezone=str(schedule["timezone"]),
            question_lag_days=int(schedule["question_lag_days"]),
            termination_lag_days=int(schedule["termination_lag_days"]),
            connection_string_env=str(database["connection_string_env"]),
            question_query=(root / paths["question_query"]).resolve(),
            termination_query=(root / paths["termination_query"]).resolve(),
            history=(root / paths["history"]).resolve(),
            depot=(root / paths["depot"]).resolve(),
        )
