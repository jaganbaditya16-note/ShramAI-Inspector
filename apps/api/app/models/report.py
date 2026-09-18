"""Report snapshots and the append-only audit trail."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.helpers import TZDateTime, new_uuid, utcnow
from ..db.session import Base

# SQLite only treats plain INTEGER primary keys as rowid aliases, so use a
# dialect variant for the autoincrement audit id.
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")


class Report(Base):
    """Immutable snapshot of a screening scorecard at generation time."""

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(new_uuid()))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    score: Mapped[int] = mapped_column(Integer)
    risk_level: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)

    case = relationship("Case", back_populates="reports")

    __table_args__ = (Index("ix_reports_case_created", "case_id", "created_at"),)


class AuditEvent(Base):
    """Append-only audit trail. Never updated or deleted by application code."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    org_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    case_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_label: Mapped[str] = mapped_column(String(160), default="system")
    action: Mapped[str] = mapped_column(String(80), index=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    request_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)

    __table_args__ = (Index("ix_audit_org_created", "org_id", "created_at"),)
