"""Authentication endpoints (cookie sessions). Used when auth_mode=required|oidc.

Two identity providers can create sessions:
- password login (``/auth/login``, local provider — break-glass under SSO);
- OIDC SSO (``/auth/oidc/login`` → provider → ``/auth/oidc/callback``).

Both mint a fresh opaque token (fixation impossible: no token is ever reused
or upgraded) and go through the same ``auth_sessions`` machinery, so request
resolution, RBAC, tenancy and IDOR rules are identical for every provider.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.errors import AppError, Unauthorized
from ...core.security import (
    SESSION_COOKIE_NAME,
    Principal,
    create_session,
    hash_password,
    password_policy_error,
    revoke_session,
    verify_password,
)
from ...db.helpers import utcnow
from ...db.session import get_db
from ...models import User
from ...schemas import LoginRequest, UserOut
from ...services import audit_service
from ...services.identity import (
    STATE_COOKIE_NAME,
    SSORejected,
    get_identity_provider,
)
from ...services.identity.provisioning import upsert_identity_user
from ..deps import get_principal, rate_limit_auth

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_minutes * 60,
        path="/",
    )


def _clear_cookie(response: Response, key: str) -> None:
    response.delete_cookie(
        key, path="/", httponly=True, secure=settings.cookie_secure, samesite="lax"
    )


def _user_out(principal: Principal) -> UserOut:
    assert principal.user is not None and principal.org is not None
    return UserOut(
        id=principal.user.id,
        email=principal.user.email,
        name=principal.user.name,
        role=principal.user.role,
        org_id=principal.org.id,
        is_demo=False,
    )


@router.post("/login", response_model=UserOut, dependencies=[Depends(rate_limit_auth)])
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> UserOut:
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    # Uniform failure message and constant-ish work: verify against a dummy
    # hash when the user does not exist to avoid a user-enumeration oracle.
    if user is None or not user.is_active:
        verify_password(payload.password, hash_password("dummy-counter-match-value"))
        audit_service.record(db, action="auth_login_failed", org_id=None,
                             detail={"reason": "unknown_user"})
        raise Unauthorized("Invalid email or password.")
    if not verify_password(payload.password, user.password_hash):
        audit_service.record(db, action="auth_login_failed", org_id=user.org_id,
                             detail={"reason": "bad_password"})
        raise Unauthorized("Invalid email or password.")
    _, token = create_session(db, user)
    user.last_login_at = utcnow()
    db.commit()
    principal = Principal(user=user, org=user.org, role=user.role)
    audit_service.record(db, action="auth_login", org_id=user.org_id, actor=principal)
    _set_session_cookie(response, token)
    return _user_out(principal)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db),
           principal: Principal = Depends(get_principal)) -> dict:
    if principal.auth_session is not None:
        revoke_session(db, principal.auth_session)
        audit_service.record(db, action="auth_logout", org_id=principal.org_id, actor=principal)
        db.commit()
    _clear_cookie(response, SESSION_COOKIE_NAME)
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
def me(principal: Principal = Depends(get_principal)) -> UserOut:
    if principal.is_demo or principal.user is None or principal.org is None:
        return UserOut(
            id="demo", email="demo@shramai.local", name=settings.demo_user_name,
            role="inspector", org_id=principal.org_id or "demo", is_demo=True,
        )
    return _user_out(principal)


def validate_password_or_raise(password: str) -> None:
    error = password_policy_error(password)
    if error:
        raise AppError(error, code="weak_password", status_code=422)


# --- OIDC / enterprise SSO -------------------------------------------------------

def _safe_relative(path: str) -> bool:
    """Only same-origin relative paths are valid post-login targets."""
    return path.startswith("/") and not path.startswith("//") and "\\" not in path


@router.get("/oidc/login")
def oidc_login() -> RedirectResponse:
    """Start the OIDC authorization-code flow (state/nonce/PKCE in a signed
    HttpOnly cookie; the provider URL is built server-side)."""
    provider = get_identity_provider()
    if provider is None:
        raise AppError("SSO is not enabled on this deployment.", code="sso_disabled", status_code=404)
    challenge = provider.begin_login()
    response = RedirectResponse(challenge.authorization_url, status_code=307)
    response.set_cookie(
        key=challenge.cookie_name,
        value=challenge.cookie_value,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=challenge.cookie_max_age,
        path="/",
    )
    return response


@router.get("/oidc/callback")
def oidc_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    provider = get_identity_provider()
    if provider is None:
        raise AppError("SSO is not enabled on this deployment.", code="sso_disabled", status_code=404)
    cookie_value = request.cookies.get(STATE_COOKIE_NAME)
    response = RedirectResponse(
        settings.oidc_post_login_redirect if _safe_relative(settings.oidc_post_login_redirect) else "/",
        status_code=303,
    )
    _clear_cookie(response, STATE_COOKIE_NAME)
    if error or not code or not state or not cookie_value:
        audit_service.record(db, action="auth_sso_failed", org_id=None,
                             detail={"reason": "incomplete_callback"})
        raise Unauthorized("Single sign-on could not be completed; try signing in again.")
    try:
        identity = provider.complete_login(code, state, cookie_value)
    except SSORejected as exc:
        audit_service.record(db, action="auth_sso_failed", org_id=None,
                             detail={"reason": "rejected"})
        db.commit()
        raise Unauthorized("Single sign-on could not be completed; try signing in again.") from exc
    user = upsert_identity_user(db, identity)
    _, token = create_session(db, user)
    user.last_login_at = utcnow()
    db.commit()
    principal = Principal(user=user, org=user.org, role=user.role)
    audit_service.record(
        db, action="auth_login", org_id=user.org_id, actor=principal,
        detail={"method": "oidc"},
    )
    db.commit()
    _set_session_cookie(response, token)
    return response
