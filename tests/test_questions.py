from datetime import datetime

from agira_api.models import Emitter
from agira_api.serializer import serialize_batch
from agira_daily.questions import build_question_batch


def _emitter() -> Emitter:
    return Emitter(
        country_code="250",
        company_code="0703",
        internal_company_code="ASUNI",
    )


def test_natural_person_gets_every_applicable_correspondence_family() -> None:
    batch = build_question_batch(
        [
            {
                "idcontrat": 1,
                "numero_police": "POL-123",
                "nom": "KOWALKOWSKI",
                "prenom": "FLORIAN",
                "date_naissance": "1991-01-28",
                "code_postal": "77500",
                "permis_date_obtention": "20012014",
                "immatriculation": "GQ-164-VX",
                "est_personne_morale": False,
            }
        ],
        environment="test",
        account_code="AC000189",
        sequence=1,
        emitter=_emitter(),
        emitted_at=datetime(2026, 9, 18, 23, 0),
    )

    assert [question.query_id[-3:] for question in batch.questions] == [
        "C01",
        "C03",
        "C04",
        "C05",
        "C06",
        "C07",
    ]
    rendered = serialize_batch(batch).payload.decode("windows-1252")
    family_04_line = rendered.splitlines()[2]
    assert "00011991" in family_04_line


def test_legal_entity_uses_registration_and_siren_only() -> None:
    batch = build_question_batch(
        [
            {
                "numero_police": "LEGAL-1",
                "nom": "EXAMPLE SAS",
                "prenom": "MUST BE IGNORED",
                "date_naissance": "1990-01-01",
                "permis_date_obtention": "2010-01-01",
                "immatriculation": "AA-111-AA",
                "est_personne_morale": True,
                "siren": "123456789",
            }
        ],
        environment="test",
        account_code="AC000189",
        sequence=1,
        emitter=_emitter(),
        emitted_at=datetime(2026, 9, 18, 23, 0),
    )

    assert [question.query_id[-3:] for question in batch.questions] == ["C07", "C08"]
    assert all(question.criteria.birth_date is None for question in batch.questions)
