from agira_api.parser import parse_reply_bytes
from agira_api.translators import translate_response_bytes

def _an(value: str, width: int) -> str:
    return value.ljust(width)


def _functional_reply_line() -> bytes:
    q01 = (
        "Q01"
        + (" " * 6)
        + (" " * 20)
        + _an("KOWALKOWSKI", 20)
        + (" " * 20)
        + _an("FLORIAN", 12)
        + "28011991"
        + "77500"
        + "20012014"
        + _an("GQ-164-VX", 12)
        + (" " * 9)
    )
    company = "250" + _an("0703", 6) + _an("ASUNI", 5)
    q00 = "Q00" + company + (" " * 3) + (" " * 40) + (" " * 12)
    match = "006" + "01" + _an("NOM+PRENOM", 32)
    assert len(q01) == 123
    assert len(q00) == 72
    return (q01 + q00 + match).encode("windows-1252") + b"\r\n"


def _complete_response_line() -> bytes:
    company = "250" + _an("0703", 6) + _an("ASUNI", 5)
    std = "STD" + "C" + company + "   " + "20260911050000" + "T"
    q00 = "Q00" + company + _an("AXA-Q-000001", 40) + _an("123", 12)
    match = "006" + "01" + _an("NOM+PRENOM", 32)
    record_id = "000" + company + _an("AXA-RECORD-1", 40)
    contract = "001" + company + _an("POLICY-1", 20) + "01012025" + "1,00"
    person = (
        "002"
        + "S"
        + _an("DUPONT", 20)
        + _an("ALICE", 12)
        + " "
        + "12051990"
        + _an("10 RUE EXEMPLE", 32)
        + (" " * 96)
        + "75001"
        + _an("PARIS", 26)
        + (" " * 9)
        + (" " * 5)
        + _an("LICENCE-1", 12)
        + "16072008"
    )
    termination = "003" + "5" + "03092026"
    vehicle = "005" + "0" + _an("AB-123-CD", 12) + "XXX" + "TYPE01" + "SERIAL01"
    tail = std + q00 + match + record_id + contract + person + termination + vehicle
    total = 42 + len(tail)
    stm = "STM" + "AGREPO" + "00" + "T" + f"{total:05d}" + (" " * 25)
    line = (stm + tail).encode("windows-1252")
    assert len(std) == 36
    assert len(q00) == 69
    assert len(person) == 238
    assert len(line) == total
    return line


def test_parses_supplied_functional_reply_with_warning() -> None:
    parsed = parse_reply_bytes(
        _functional_reply_line(),
        source_filename="WINDEV-FUNCTIONAL-REPLY.TXT",
    )

    assert parsed["line_count"] == 1
    assert parsed["message_count"] == 1
    assert parsed["file_errors"] == []
    message = parsed["messages"][0]
    assert message["layout"] == "functional_only_compatibility"
    assert message["criteria"]["last_name_or_company_name"] == "KOWALKOWSKI"
    assert message["criteria"]["first_name"] == "FLORIAN"
    assert message["criteria"]["birth_date"]["iso"] == "1991-01-28"
    assert message["matches"] == [
        {"segment": "006", "match_code": "01", "match_label": "NOM+PRENOM"}
    ]
    assert message["query_identification"]["observed_width"] == 72
    assert len(parsed["warnings"]) == 3


def test_parses_complete_agira_response_into_conversation() -> None:
    parsed = parse_reply_bytes(
        _complete_response_line() + b"\r\n",
        source_filename="response.TXT",
    )

    assert parsed["file_errors"] == []
    assert parsed["message_count"] == 1
    message = parsed["messages"][0]
    assert message["message_type"] == "AGREPO"
    assert message["record"]["contract"]["contract_number"] == "POLICY-1"
    assert message["record"]["persons"][0]["birth_date"]["iso"] == "1990-05-12"
    assert message["record"]["vehicle"]["registration_number"] == "AB-123-CD"
    assert parsed["conversations"][0]["query_id"] == "AXA-Q-000001"
    assert len(parsed["conversations"][0]["results"]) == 1


def test_clear_response_translation_includes_all_business_sections() -> None:
    translated = translate_response_bytes(
        _complete_response_line() + b"\r\n",
        source_filename="response.TXT",
    )

    assert translated["summary"]["statuses"] == {"matched": 1}
    assert translated["summary"]["returned_record_count"] == 1
    conversation = translated["conversations"][0]
    assert conversation["match_reasons"][0]["match_code"] == "01"
    record = conversation["records"][0]
    assert record["contract"]["contract_number"] == "POLICY-1"
    assert record["persons"][0]["name_or_company_name"] == "DUPONT"
    assert record["termination"]["reason_code"] == "5"
    assert record["claims"] == []
    assert record["vehicle"]["registration_number"] == "AB-123-CD"
    assert record["cnil"] is None
    # legacy query id shape: the field is present but nothing is claimed
    assert conversation["query_id"] == "AXA-Q-000001"
    assert conversation["query_id_parts"] is None


def test_query_id_parts_are_extracted_from_sql_csv_ids() -> None:
    from agira_api.translators import _query_id_parts

    assert _query_id_parts("GA433165-20260916-000001-C07") == {
        "numero_police": "GA433165",
        "emitted_date": "20260916",
        "row": "000001",
        "correspondence_code": "07",
    }
    # sanitized police numbers may contain dashes
    assert _query_id_parts("POL-1-20260916-000002-C04")["numero_police"] == "POL-1"
    assert _query_id_parts("CHECK-910001-C04") is None
    assert _query_id_parts(None) is None


def test_bad_line_is_reported_without_aborting_file() -> None:
    parsed = parse_reply_bytes(
        b"BAD LINE\r\n" + _complete_response_line() + b"\r\n",
        source_filename="mixed.TXT",
    )

    assert parsed["line_count"] == 2
    assert parsed["message_count"] == 1
    assert parsed["file_errors"][0]["line"] == 1
