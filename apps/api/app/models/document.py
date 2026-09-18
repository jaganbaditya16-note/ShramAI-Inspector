"""Documents, extraction/processing jobs and model runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.helpers import TZDateTime, new_uuid, utcnow
from ..db.session import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(new_uuid()))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    # Storage key is server-generated (UUID path). Never exposed to clients.
    storage_key: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    # queued -> processing -> processed | failed
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text_chars: Mapped[int] = mapped_column(Integer, default=0)
    extraction_method: Mapped[str] = mapped_column(String(20), default="none")
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    # Page map: [{"page": 1, "start": 0, "end": 920}, ...] offsets into extracted_text.
    page_map: Mapped[list[dict[str, int]] | None] = mapped_column(JSON, nullable=True)
    doc_type: Mapped[str] = mapped_column(String(24), default="unknown", index=True)
    doc_type_confidence: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)

    case = relationship("Case", back_populates="documents")
    findings = relationship("Finding", back_populates="document", cascade="all, delete-orphan")
    jobs = relationship("ProcessingJob", back_populates="document", cascade="all, delete-orphan")
    model_runs = relationship("ModelRun", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_documents_case_status", "case_id", "status"),)


class ProcessingJob(Base):
    """One unit of background document processing (extraction -> findings)."""

    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(new_uuid()))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    # queued -> running -> succeeded | failed
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)

    document = relationship("Document", back_populates="jobs")


class ModelRun(Base):
    """Traceability record for every AI provider invocation (AI governance)."""

    __tablename__ = "model_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(new_uuid()))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120), default="")
    # disabled | succeeded | unavailable | error
    status: Mapped[str] = mapped_column(String(24))
    prompt_version: Mapped[str] = mapped_column(String(40), default="")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    findings_produced: Mapped[int] = mapped_column(Integer, default=0)
    findings_rejected: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)

    document = relationship("Document", back_populates="model_runs")
