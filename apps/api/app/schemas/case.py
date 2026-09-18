"""Case schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CaseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    establishment_name: str = Field(default="", max_length=200)
    establishment_reference: str | None = Field(default=None, max_length=120)
    notes: str = Field(default="", max_length=4000)


class CaseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    establishment_name: str | None = Field(default=None, max_length=200)
    establishment_reference: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)
    status: str | None = Field(default=None, pattern="^(draft|in_review|closed)$")


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_code: str
    title: str
    establishment_name: str
    establishment_reference: str | None
    status: str
    notes: str
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class CaseListItem(CaseOut):
    document_count: int
    finding_count: int


class CaseList(BaseModel):
    items: list[CaseListItem]
    meta: dict[str, int]
