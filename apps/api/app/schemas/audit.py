"""Audit and dashboard schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    actor_label: str
    case_id: str | None
    detail: dict[str, Any]
    request_id: str
    created_at: datetime


class AuditList(BaseModel):
    items: list[AuditEventOut]
    meta: dict[str, int]


class DashboardSummary(BaseModel):
    cases_total: int
    cases_by_status: dict[str, int]
    documents_total: int
    documents_failed: int
    findings_total: int
    findings_by_status: dict[str, int]
    findings_by_severity: dict[str, int]
    ai_runs_total: int
    recent_activity: list[AuditEventOut]
