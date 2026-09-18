"""Inspection cases."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.helpers import TZDateTime, new_uuid, utcnow
from ..db.session import Base


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(new_uuid()))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    display_code: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(200))
    establishment_name: Mapped[str] = mapped_column(String(200), default="")
    establishment_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # draft -> in_review -> closed (reopen allowed)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)

    documents = relationship("Document", back_populates="case", cascade="all, delete-orphan")
    findings = relationship("Finding", back_populates="case", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="case", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_cases_org_status", "org_id", "status"),
        Index("ix_cases_org_deleted", "org_id", "deleted_at"),
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
