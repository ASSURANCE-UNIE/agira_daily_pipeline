from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Emitter(StrictModel):
    country_code: str = Field(default="250", pattern=r"^\d{3}$")
    company_code: ShortText = Field(max_length=6)
    internal_company_code: str = Field(default="", max_length=5)


class MonthYearDate(StrictModel):
    """Partial date (month + year), serialized as `00MMYYYY`.

    AGIRA match family 04 (NOM+NAISSANCE) requires the birth *month and year*;
    a full DDMMYYYY date there is rejected with "AU MOINS UN CRITERE".
    """

    month: int = Field(ge=1, le=12)
    year: int = Field(ge=1000, le=9999)


class QueryCriteria(StrictModel):
    previous_insurer_company_code: str | None = Field(default=None, max_length=6)
    contract_number: str | None = Field(default=None, max_length=20)
    last_name_or_company_name: str | None = Field(default=None, max_length=20)
    birth_or_maiden_name: str | None = Field(default=None, max_length=20)
    first_name: str | None = Field(default=None, max_length=12)
    birth_date: date | MonthYearDate | None = None
    residence_postal_code: str | None = Field(default=None, max_length=5)
    driving_licence_date: date | None = None
    registration_number: str | None = Field(default=None, max_length=12)
    siren: str | None = Field(default=None, pattern=r"^\d{9}$")

    @model_validator(mode="after")
    def has_supported_match_family(self) -> "QueryCriteria":
        has_previous_policy = bool(
            self.previous_insurer_company_code and self.contract_number
        )
        has_name_first_postal = bool(
            self.last_name_or_company_name
            and self.first_name
            and self.residence_postal_code
        )
        has_name_birth = bool(self.last_name_or_company_name and self.birth_date)
        has_name_licence = bool(
            self.last_name_or_company_name and self.driving_licence_date
        )
        has_vehicle = bool(self.registration_number)
        has_company = bool(self.siren)
        if not any(
            (
                has_previous_policy,
                has_name_first_postal,
                has_name_birth,
                has_name_licence,
                has_vehicle,
                has_company,
            )
        ):
            raise ValueError(
                "criteria do not form an AGIRA match family; provide previous "
                "insurer + contract, an allowed name combination, a registration, "
                "or a SIREN"
            )
        return self


class Question(StrictModel):
    query_id: ShortText = Field(max_length=40)
    criteria: QueryCriteria


class QuestionBatch(StrictModel):
    environment: Literal["test", "production"] = "test"
    account_code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    sequence: int = Field(default=1, ge=1, le=9999)
    emitter: Emitter
    questions: list[Question] = Field(min_length=1)
    emitted_at: datetime | None = None
    output_filename: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_.-]+$",
        max_length=180,
    )

    @model_validator(mode="after")
    def query_ids_are_unique(self) -> "QuestionBatch":
        identifiers = [question.query_id for question in self.questions]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("query_id values must be unique within a batch")
        return self


class ExistingReplyFile(StrictModel):
    input_filename: str = Field(
        pattern=r"^[A-Za-z0-9_.-]+$",
        min_length=1,
        max_length=180,
    )


class RenderedBatch(StrictModel):
    batch_id: str
    filename: str
    path: str
    environment: Literal["test", "production"]
    application_code: str
    encoding: str
    line_ending: Literal["CRLF"] = "CRLF"
    message_count: int
    byte_length: int
    sha256: str
    query_ids: list[str]


class TranslationArtifact(StrictModel):
    source_filename: str
    parsed_filename: str
    parsed_path: str
    line_count: int
    message_count: int
    warning_count: int
    error_count: int
    data: dict


class TerminationContract(StrictModel):
    insurer: Emitter
    contract_number: ShortText = Field(max_length=20)
    effective_date: date
    bonus_malus_coefficient: str | None = Field(
        default=None,
        pattern=r"^\d,\d{2}$",
        description="AGIRA CRM format, for example 1,00",
    )


class TerminationPerson(StrictModel):
    role: Literal["subscriber", "driver"]
    person_kind: Literal["natural_person", "legal_entity"] = "natural_person"
    name_or_company_name: ShortText = Field(max_length=20)
    first_name: str | None = Field(default=None, max_length=12)
    birth_date: date | None = None
    address_lines: list[ShortText] = Field(min_length=1, max_length=4)
    postal_code: ShortText = Field(min_length=2, max_length=5)
    city: ShortText = Field(max_length=26)
    siren: str | None = Field(default=None, pattern=r"^\d{9}$")
    licence_issue_postal_code: str | None = Field(
        default=None, min_length=2, max_length=5
    )
    driving_licence_number: str | None = Field(default=None, max_length=12)
    driving_licence_date: date | None = None

    @model_validator(mode="after")
    def validate_person_kind(self) -> "TerminationPerson":
        if self.person_kind == "natural_person" and self.birth_date is None:
            raise ValueError("birth_date is required for a natural person")
        if self.person_kind == "legal_entity" and (
            self.driving_licence_number or self.driving_licence_date
        ):
            raise ValueError("a legal entity cannot have driving-licence information")
        return self


class TerminationDetails(StrictModel):
    reason_code: Literal["1", "2", "3", "4", "5"]
    termination_date: date


class TerminationClaim(StrictModel):
    claim_number: ShortText = Field(max_length=20)
    nature_code: Literal["M", "C"]
    claim_date: date
    guarantee_code: Literal["01", "04", "05", "06", "07", "99"]
    responsibility_percent: int = Field(ge=0, le=100)
    driver_last_name: str | None = Field(default=None, max_length=20)
    driver_first_name: str | None = Field(default=None, max_length=12)


class TerminationVehicle(StrictModel):
    category_code: Literal["0", "1", "2", "3", "4", "5", "6", "7"]
    registration_number: ShortText = Field(max_length=12)
    manufacturer_code: str | None = Field(default=None, max_length=3)
    type_mine: str | None = Field(default=None, max_length=6)
    serial_number: str | None = Field(default=None, max_length=8)


class TerminationRecord(StrictModel):
    operation: Literal["create", "modify", "delete"]
    company_record_id: str | None = Field(default=None, max_length=40)
    record_company: Emitter
    contract: TerminationContract | None = None
    persons: list[TerminationPerson] = Field(default_factory=list, max_length=5)
    termination: TerminationDetails | None = None
    claims: list[TerminationClaim] = Field(default_factory=list, max_length=10)
    vehicle: TerminationVehicle | None = None
    cnil_comment: str | None = Field(
        default=None,
        max_length=160,
        description=(
            "AGIRA 007 comment, only when the insured has actually exercised "
            "their right of rectification"
        ),
    )
    cnil_rectification_confirmed: bool = False

    @model_validator(mode="after")
    def validate_operation(self) -> "TerminationRecord":
        if self.operation in {"modify", "delete"} and not self.company_record_id:
            raise ValueError(
                "company_record_id is required for modification or deletion"
            )
        detail_values = (
            self.contract,
            self.persons,
            self.termination,
            self.claims,
            self.vehicle,
            self.cnil_comment,
            self.cnil_rectification_confirmed,
        )
        if self.operation == "delete":
            if any(detail_values):
                raise ValueError(
                    "a deletion contains only the record identification"
                )
            return self
        if not self.contract or not self.persons or not self.termination or not self.vehicle:
            raise ValueError(
                "creation and modification require contract, persons, termination, and vehicle"
            )
        if self.cnil_comment and not self.cnil_rectification_confirmed:
            raise ValueError(
                "cnil_rectification_confirmed must be true when cnil_comment is supplied"
            )
        if self.cnil_rectification_confirmed and not self.cnil_comment:
            raise ValueError(
                "cnil_comment is required when cnil_rectification_confirmed is true"
            )
        if self.termination.reason_code == "3" and not self.claims:
            raise ValueError("at least one claim is required when reason_code is 3")
        if self.vehicle.category_code in {"0", "2"} and not (
            self.contract.bonus_malus_coefficient
        ):
            raise ValueError(
                "bonus_malus_coefficient is required for vehicle category 0 or 2"
            )
        return self


class TerminationBatch(StrictModel):
    environment: Literal["test", "production"] = "test"
    account_code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    sequence: int = Field(default=1, ge=1, le=9999)
    emitter: Emitter
    records: list[TerminationRecord] = Field(min_length=1)
    emitted_at: datetime | None = None
    output_filename: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_.-]+$",
        max_length=180,
    )


class RenderedTerminationBatch(StrictModel):
    batch_id: str
    filename: str
    path: str
    environment: Literal["test", "production"]
    application_code: str
    encoding: str
    line_ending: Literal["CRLF"] = "CRLF"
    record_count: int
    operation_counts: dict[str, int]
    byte_length: int
    sha256: str
    company_record_ids: list[str | None]
