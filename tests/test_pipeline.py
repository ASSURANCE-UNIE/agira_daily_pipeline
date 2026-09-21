import json
from datetime import date
from pathlib import Path

import pytest

from agira_daily.config import PipelineConfig
from agira_daily.runner import run_feed


def _settings(tmp_path: Path) -> PipelineConfig:
    settings = tmp_path / "settings.toml"
    settings.write_text(
        """
[agira]
environment = "test"
account_code = "AC000189"
country_code = "250"
company_code = "0703"
internal_company_code = "ASUNI"
question_sequence = 1
termination_sequence = 2
[schedule]
timezone = "Europe/Paris"
question_lag_days = 1
termination_lag_days = 35
[database]
connection_string_env = "TEST_CONNECTION"
[paths]
question_query = "queries/questions/query.sql"
termination_query = "queries/terminations/query.sql"
history = "data/history"
depot = "data/depot"
""".strip(),
        encoding="utf-8",
    )
    return PipelineConfig.load(settings)


def _question_rows() -> list[dict]:
    return [
        {
            "numero_police": "POL-1",
            "nom": "DUPONT",
            "prenom": "ALICE",
            "date_naissance": "1990-05-12",
            "code_postal": "75001",
            "permis_date_obtention": "2008-07-16",
            "immatriculation": "AB-123-CD",
            "est_personne_morale": False,
        }
    ]


def _termination_rows() -> list[dict]:
    record = {
        "operation": "create",
        "company_record_id": "REC-1",
        "record_company": {"company_code": "0200"},
        "contract": {
            "insurer": {"company_code": "0200"},
            "contract_number": "POLICY-1",
            "effective_date": "2024-01-01",
            "bonus_malus_coefficient": "1,00",
        },
        "persons": [
            {
                "role": "subscriber",
                "name_or_company_name": "DUPONT",
                "first_name": "ALICE",
                "birth_date": "1990-05-12",
                "address_lines": ["1 RUE TEST"],
                "postal_code": "75001",
                "city": "PARIS",
            }
        ],
        "termination": {"reason_code": "5", "termination_date": "2026-08-14"},
        "vehicle": {"category_code": "0", "registration_number": "AB-123-CD"},
    }
    return [{"record_json": json.dumps(record)}]


def test_question_run_archives_json_txt_manifest_and_publishes_depot(tmp_path: Path) -> None:
    config = _settings(tmp_path)
    result = run_feed(
        "questions",
        config=config,
        run_date=date(2026, 9, 18),
        rows=_question_rows(),
    )

    assert result.status == "published"
    assert result.history_dir == tmp_path / "data/history/questions/2026-09-18"
    assert result.json_path and result.json_path.is_file()
    assert result.txt_path and result.txt_path.is_file()
    assert result.depot_path and result.depot_path.read_bytes() == result.txt_path.read_bytes()
    manifest = json.loads((result.history_dir / "manifest.json").read_text())
    assert manifest["source_date"] == "2026-09-17"
    assert manifest["source_row_count"] == 1
    assert manifest["agira_item_count"] == 6

    with pytest.raises(FileExistsError, match="history already exists"):
        run_feed(
            "questions",
            config=config,
            run_date=date(2026, 9, 18),
            rows=_question_rows(),
        )


def test_termination_run_uses_35_day_source_and_distinct_sequence(tmp_path: Path) -> None:
    config = _settings(tmp_path)
    result = run_feed(
        "terminations",
        config=config,
        run_date=date(2026, 9, 18),
        rows=_termination_rows(),
    )

    manifest = json.loads((result.history_dir / "manifest.json").read_text())
    assert manifest["source_date"] == "2026-08-14"
    assert result.txt_path and "202609180002.TXT" in result.txt_path.name


def test_empty_day_has_manifest_but_no_depot_file(tmp_path: Path) -> None:
    config = _settings(tmp_path)
    result = run_feed(
        "questions",
        config=config,
        run_date=date(2026, 9, 18),
        rows=[],
    )

    assert result.status == "empty"
    assert result.depot_path is None
    assert json.loads((result.history_dir / "manifest.json").read_text())["status"] == "empty"
    assert not (tmp_path / "data/depot/questions").exists()
