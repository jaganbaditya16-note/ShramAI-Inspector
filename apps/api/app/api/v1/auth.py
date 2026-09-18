"""Authentication endpoints (cookie sessions). Used when auth_mode=required."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
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
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
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
