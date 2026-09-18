"""Finding schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    rule_id: str
    rule_version: str
    origin: str
    title: str
    severity: str
    status: str
    explanation: str
    evidence_kind: str
    evidence_quote: str
    page: int | None
    char_start: int | None
    char_end: int | None
    confidence: int
    ai_metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("ai_metadata", "metadata_json"),
        serialization_alias="ai_metadata",
    )
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_note: str | None
    created_at: datetime


class FindingList(BaseModel):
    items: list[FindingOut]
    meta: dict[str, int]


class FindingReview(BaseModel):
    status: str = Field(pattern="^(confirmed|dismissed|needs_review)$")
    note: str | None = Field(default=None, max_length=2000)
