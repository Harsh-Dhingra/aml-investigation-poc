from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Transaction(BaseModel):
    model_config = ConfigDict(extra="allow")
    transaction_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    txn_ts: datetime
    txn_type: str
    direction: Literal["INCOMING", "OUTGOING"]
    amount: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    currency: Literal["USD"]
    cash_flag: bool
    counterparty_id: str = ""
    counterparty_country: str = ""
    branch_state: str = ""
    branch_id: str = ""
    depositor_id: str = ""
    purpose_field: str = ""
    invoice_id: str = ""
    is_round_amount: bool = False

    @field_validator("txn_ts")
    @classmethod
    def normalize_time(cls, value):
        # Source timestamps have no offset. Treat them as the demo's UTC event clock.
        if value.tzinfo:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value


class Finding(BaseModel):
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class Assessment(BaseModel):
    summary: str = Field(min_length=1)
    summary_evidence_ids: list[str] = Field(min_length=1)
    findings: list[Finding] = Field(min_length=1)
    innocent_explanation: str
    recommendation: Literal["clear", "request_info", "escalate"]


class ReviewDecision(BaseModel):
    action: Literal["clear", "request_info", "escalate"]
    reason: str = Field(min_length=5, max_length=4000)
    investigator: str = Field(min_length=2, max_length=120)
    case_id: str
    sar_narrative: str | None = Field(default=None, max_length=20000)

    @field_validator("reason", "investigator")
    @classmethod
    def nonblank(cls, value, info):
        if len(value.strip()) < (5 if info.field_name == "reason" else 2):
            raise ValueError("Enter a meaningful value")
        return value.strip()


class ReplayRequest(BaseModel):
    events_per_second: float = Field(default=50, gt=0, le=500)
    auto_investigate: bool = True


class EvidenceDocument(BaseModel):
    document_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    customer_id: str
    title: str = Field(min_length=1)
    content: str = Field(min_length=1, max_length=20000)
    evidence_types: list[str] = Field(min_length=1)
    transaction_ids: list[str] = Field(default_factory=list)
    readable: bool = True
    extraction_confidence: float = Field(default=1, ge=0, le=1)
    origin: Literal["investigator_supplied", "synthetic_fixture", "model_extraction", "pdf_text"] = (
        "investigator_supplied"
    )
    source_sha256: str | None = None
    extracted_fields: dict = Field(default_factory=dict)
    demonstration_resolution: Literal["unresolved", "documented_legitimate"] = "unresolved"
