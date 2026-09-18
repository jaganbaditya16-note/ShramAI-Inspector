"""Findings: deterministic or AI-assisted screening results with provenance,
evidence anchoring and a human review state machine.

AI governance invariants enforced by the writing services:
- origin is always "rule" or "ai"; AI findings can never auto-confirm.
- AI findings are only stored when their evidence quote is verifiable in the
  extracted document text (grounded); otherwise they are rejected and counted
  on the ModelRun row.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.helpers import TZDateTime, new_uuid, utcnow
from ..db.session import Base


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(new_uuid()))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)

    rule_id: Mapped[str] = mapped_column(String(80))
    rule_version: Mapped[str] = mapped_column(String(40), default="")
    origin: Mapped[str] = mapped_column(String(10), default="rule")  # rule | ai
    title: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(20), default="low")  # low | medium | high
    # needs_review -> confirmed | dismissed (reversible)
    status: Mapped[str] = mapped_column(String(24), default="needs_review", index=True)
    explanation: Mapped[str] = mapped_column(Text)
    # quote | absence (absence = the check found evidence MISSING, so there is
    # no quotable snippet; the explanation carries the audit context).
    evidence_kind: Mapped[str] = mapped_column(String(12), default="absence")
    evidence_quote: Mapped[str] = mapped_column(Text, default="")
    evidence_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, default=0)  # 0..100
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    reviewed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow)

    case = relationship("Case", back_populates="findings")
    document = relationship("Document", back_populates="findings")
    reviewer = relationship("User", foreign_keys=[reviewed_by])

    __table_args__ = (
        Index("ix_findings_case_status", "case_id", "status"),
        Index("ix_findings_document_rule", "document_id", "rule_id"),
    )

    @property
    def is_reviewed(self) -> bool:
        return self.status in {"confirmed", "dismissed"}
