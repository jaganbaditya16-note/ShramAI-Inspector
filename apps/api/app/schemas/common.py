"""Shared API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorEnvelope(BaseModel):
    """Consistent error shape returned by every failure."""

    error: dict[str, Any]


class PaginatedMeta(BaseModel):
    total: int
    limit: int
    offset: int
