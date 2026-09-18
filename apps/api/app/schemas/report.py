"""Report schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ReportOut(BaseModel):
    id: str
    case_id: str
    score: int
    risk_level: str
    created_at: datetime
    payload: dict[str, Any]
