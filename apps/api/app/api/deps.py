"""API dependencies: database session, authenticated principal, role guards,
pagination and rate limiting."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Query, Request

from ..core.config import settings
from ..core.errors import Forbidden, Unauthorized
from ..core.rate_limit import RateLimitRule, limiter
from ..core.security import SESSION_COOKIE_NAME, Principal, resolve_session
from ..db.session import get_db

PUBLIC_PATHS = {
    "/api/v1/health",
    "/api/v1/auth/login",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
    "/",
}


def get_principal(request: Request, db=Depends(get_db)) -> Principal:
    """Resolve the acting principal.

    ``demo`` mode injects a virtual demo principal (public demo deployments).
    ``required`` mode demands a valid session cookie.
    """
    if settings.auth_mode == "demo":
        from ..core.security import get_demo_principal

        return get_demo_principal(db)

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise Unauthorized("Authentication required.")
    resolved = resolve_session(db, token)
    if resolved is None:
        raise Unauthorized("Session is invalid or expired.")
    auth_session, user = resolved
    return Principal(
        user=user, org=user.org, role=user.role, auth_session=auth_session, is_demo=False
    )


def require_inspector(principal: Principal = Depends(get_principal)) -> Principal:
    if not principal.has_role("inspector"):
        raise Forbidden("This action requires the inspector role.")
    return principal


def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if not principal.has_role("admin"):
        raise Forbidden("This action requires the admin role.")
    return principal


@dataclass(frozen=True)
class PageParams:
    limit: int = 20
    offset: int = 0

    @classmethod
    def depends(cls, limit: int = Query(default=20, ge=1, le=100),
                offset: int = Query(default=0, ge=0)) -> PageParams:
        return cls(limit=limit, offset=offset)


def rate_limit_auth(request: Request) -> None:
    if settings.rate_limit_enabled:
        limiter.check(
            RateLimitRule("auth", settings.rate_limit_auth_per_minute),
            getattr(request.state, "client_ip", "unknown"),
        )


def rate_limit_upload(request: Request) -> None:
    if settings.rate_limit_enabled:
        limiter.check(
            RateLimitRule("upload", settings.rate_limit_upload_per_minute),
            getattr(request.state, "client_ip", "unknown"),
        )
