from datetime import datetime

import pytest
from pydantic import ValidationError

from agira_api.models import Emitter, QueryCriteria, Question, QuestionBatch
from agira_api.parser import parse_reply_bytes
from agira_api.serializer import QUESTION_MESSAGE_WIDTH, serialize_batch, serialize_question


def sample_question() -> Question:
    return Question(
        query_id="AXA-Q-000001",
        criteria=QueryCriteria(
            last_name_or_company_name="KOWALKOWSKI",
            first_name="FLORIAN",
            birth_date="1991-01-28",
            residence_postal_code="77500",
            driving_licence_date="2014-01-20",
            registration_number="GQ-164-VX",
        ),
    )


def test_complete_question_layout_and_declared_length() -> None:
    emitter = Emitter(company_code="0703", internal_company_code="ASUNI")
    line = serialize_question(
        sample_question(),
        emitter,
        datetime(2026, 9, 10, 14, 30, 0),
    )

    assert len(line) == QUESTION_MESSAGE_WIDTH == 286
    assert line[0:3] == b"STM"
    assert line[3:9] == b"AGQUES"
    assert int(line[12:17]) == len(line)
    assert line[42:45] == b"STE"
    assert line[94:97] == b"Q00"
    assert line[163:166] == b"Q01"

    parsed = parse_reply_bytes(line + b"\r\n", source_filename="question.TXT")
    message = parsed["messages"][0]
    assert message["message_type"] == "AGQUES"
    assert message["query_identification"]["company_query_identifier"] == "AXA-Q-000001"
    assert message["criteria"]["birth_date"]["iso"] == "1991-01-28"


def test_batch_uses_crlf_and_test_application_code() -> None:
    batch = QuestionBatch(
        environment="test",
        account_code="AC000189",
        sequence=2,
        emitted_at=datetime(2026, 9, 10, 14, 30, 0),
        emitter=Emitter(company_code="0703", internal_company_code="ASUNI"),
        questions=[sample_question()],
    )
    rendered = serialize_batch(batch)

    assert rendered.application_code == "HOCSFR43"
    assert rendered.filename == "RA-AC000189-HOCSFR43.AC000189_202609100002.TXT"
    assert rendered.payload.endswith(b"\r\n")
    assert rendered.payload.count(b"\r\n") == 1


def test_query_requires_supported_match_family() -> None:
    with pytest.raises(ValidationError):
        QueryCriteria(first_name="ONLY-FIRST-NAME")


def test_unencodable_character_is_rejected() -> None:
    question = Question(
        query_id="AXA-Q-EMOJI",
        criteria=QueryCriteria(registration_number="AB-123-CD"),
    )
    question.criteria.registration_number = "CAR🚗"
    with pytest.raises(ValueError, match="not representable"):
        serialize_question(
            question,
            Emitter(company_code="0703"),
            datetime(2026, 9, 10, 14, 30, 0),
        )

