"""Authentication primitives: password hashing, session tokens, principals.

Two auth modes exist:
- ``demo``  — every request receives a virtual demo principal (public demo).
- ``required`` — cookie sessions backed by ``auth_sessions`` rows, with
  organisation-scoped users and roles.

Session tokens are opaque 32-byte urlsafe strings. Only their SHA-256 hash is
persisted, so a database leak does not leak usable credentials.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db.helpers import utcnow
from ..models import AuthSession, Organization, User

_hasher = PasswordHasher()

DEMO_ROLE = "inspector"
ROLE_RANK = {"viewer": 0, "inspector": 1, "admin": 2}
VALID_ROLES = ("admin", "inspector", "viewer")

SESSION_COOKIE_NAME = "shramai_session"


# --- Passwords -----------------------------------------------------------------

def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def password_policy_error(password: str) -> str | None:
    if len(password) < 10:
        return "Password must be at least 10 characters long."
    if password.lower() in {"password", "inspector", "shramai123!"} or not any(
        c.isdigit() for c in password
    ):
        return "Password must contain a digit and must not be a common phrase."
    return None


# --- Session tokens --------------------------------------------------------------

def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: User) -> tuple[AuthSession, str]:
    token = new_session_token()
    session = AuthSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=utcnow() + timedelta(minutes=settings.session_ttl_minutes),
    )
    db.add(session)
    db.flush()
    return session, token


def resolve_session(db: Session, token: str) -> tuple[AuthSession, User] | None:
    stmt = (
        select(AuthSession, User)
        .join(User, AuthSession.user_id == User.id)
        .where(AuthSession.token_hash == hash_token(token))
    )
    row = db.execute(stmt).first()
    if row is None:
        return None
    auth_session, user = row
    if not auth_session.is_valid or not user.is_active:
        return None
    return auth_session, user


def revoke_session(db: Session, auth_session: AuthSession) -> None:
    if auth_session.revoked_at is None:
        auth_session.revoked_at = utcnow()


# --- Principals -------------------------------------------------------------------

@dataclass(frozen=True)
class Principal:
    """The actor behind the current request."""

    user: User | None
    org: Organization | None
    role: str
    auth_session: AuthSession | None = None
    is_demo: bool = False

    @property
    def user_id(self) -> str | None:
        return self.user.id if self.user else None

    @property
    def org_id(self) -> str | None:
        return self.org.id if self.org else None

    @property
    def display_name(self) -> str:
        if self.is_demo:
            return settings.demo_user_name
        return self.user.name if self.user else "system"

    def has_role(self, minimum: str) -> bool:
        return ROLE_RANK.get(self.role, -1) >= ROLE_RANK.get(minimum, 99)


def get_demo_principal(db: Session) -> Principal:
    """Return (creating if needed) the shared demo organisation and principal."""
    from ..services.demo_seed import ensure_demo_org  # local import avoids cycle

    org, user = ensure_demo_org(db)
    return Principal(user=user, org=org, role=DEMO_ROLE, is_demo=True)
