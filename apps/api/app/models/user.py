"""User accounts and authentication sessions.

Passwords are stored with Argon2id. Sessions store only the SHA-256 hash of
the opaque bearer token; the raw token lives only in the user's cookie.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.helpers import TZDateTime, new_uuid, utcnow
from ..db.session import Base

Role = str  # "admin" | "inspector" | "viewer" — validated at the schema layer


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(new_uuid()))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(160))
    # Nullable: the virtual demo principal has no credential.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)

    org = relationship("Organization")
    sessions = relationship("AuthSession", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (Index("uq_users_email", "email", unique=True),)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(new_uuid()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)

    user = relationship("User", back_populates="sessions")

    __table_args__ = (Index("uq_auth_sessions_token_hash", "token_hash", unique=True),)

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at <= utcnow())

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_valid(self) -> bool:
        return not (self.is_expired or self.is_revoked)
