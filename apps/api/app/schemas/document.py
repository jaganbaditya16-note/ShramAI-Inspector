"""Document schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class JobOut(BaseModel):
    id: str
    status: str
    error: str | None = None
    detail: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class DocumentOut(BaseModel):
    id: str
    case_id: str
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    error: str | None
    page_count: int | None
    text_chars: int
    extraction_method: str
    doc_type: str
    doc_type_confidence: int
    scan_status: str = "not_scanned"
    scan_signature: str | None = None
    scan_note: str | None = None
    created_at: datetime
    processed_at: datetime | None
    job: JobOut | None = None


class DocumentList(BaseModel):
    items: list[DocumentOut]
    meta: dict[str, int]


class UploadAccepted(BaseModel):
    """202 response: the document is registered; processing is asynchronous."""

    document: DocumentOut
    job: JobOut
    message: str
