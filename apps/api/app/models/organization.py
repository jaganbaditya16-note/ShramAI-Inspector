"""Organisation model (tenant root).

Every inspection object is scoped to an organisation so that cross-tenant
access is impossible by construction: queries always filter on org_id.
"""

from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db.helpers import TZDateTime, new_uuid, utcnow
from ..db.session import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(new_uuid()))
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[object] = mapped_column(TZDateTime, default=utcnow)

    __table_args__ = (UniqueConstraint("slug", name="uq_organizations_slug"),)
