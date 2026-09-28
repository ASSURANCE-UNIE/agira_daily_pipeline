from datetime import datetime

from fastapi.testclient import TestClient

from agira_api.main import app


def _question_payload() -> dict:
    return {
        "environment": "test",
        "account_code": "AC000189",
        "sequence": 1,
        "emitted_at": datetime(2026, 9, 10, 14, 30).isoformat(),
        "output_filename": "QUESTIONS.TXT",
        "emitter": {
            "country_code": "250",
            "company_code": "0703",
            "internal_company_code": "ASUNI",
        },
        "questions": [
            {
                "query_id": "AXA-Q-000001",
                "criteria": {"registration_number": "AB-123-CD"},
            }
        ],
    }


def test_stateless_json_to_agira_and_back() -> None:
    with TestClient(app) as client:
        rendered = client.post("/v1/json-to-agira", json=_question_payload())

        assert rendered.status_code == 200, rendered.text
        assert rendered.content.startswith(b"STMAGQUES")
        assert rendered.headers["x-agira-document-type"] == "questions"
        assert 'filename="QUESTIONS.TXT"' in rendered.headers["content-disposition"]

        translated = client.post(
            "/v1/agira-to-json?filename=QUESTIONS.TXT&kind=questions",
            content=rendered.content,
            headers={"content-type": "application/octet-stream"},
        )

        assert translated.status_code == 200, translated.text
        body = translated.json()
        assert body["summary"]["is_valid"] is True
        assert body["questions"][0]["query_id"] == "AXA-Q-000001"


def test_json_to_agira_rejects_ambiguous_document() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/v1/json-to-agira",
            json={"questions": [], "records": []},
        )
    assert response.status_code == 422
    assert "exactly one discriminator" in response.json()["detail"]


def test_agira_to_json_does_not_write_uploaded_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with TestClient(app) as client:
        rendered = client.post("/v1/json-to-agira", json=_question_payload())
        response = client.post(
            "/v1/agira-to-json?filename=NO-SIDE-EFFECT.TXT",
            content=rendered.content,
        )
    assert response.status_code == 200
    assert list(tmp_path.iterdir()) == []
