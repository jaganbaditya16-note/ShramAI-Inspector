"""Provisioning: turn a verified outside identity into a local user.

Matching rules (defence against account takeover):
1. Exact federated match on (idp_issuer, idp_subject).
2. Otherwise, if the identity's email is **verified**, link the existing
   local account with that email (records the federated identity).
3. Otherwise create a new user in the configured SSO organisation with the
   configured default role. Role/group claims from the provider are recorded
   but never silently mapped to local roles — that mapping is an explicit
   operational decision, not something an IdP can grant itself.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.security import VALID_ROLES
from ...models import Organization, User
from .base import Identity, SSORejected


def ensure_sso_org(db: Session, name: str) -> Organization:
    org = db.scalar(select(Organization).where(Organization.name == name))
    if org is None:
        base_slug = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-") or "org"
        slug = base_slug
        counter = 2
        while db.scalar(select(Organization.id).where(Organization.slug == slug)):
            slug = f"{base_slug}-{counter}"
            counter += 1
        org = Organization(name=name, slug=slug)
        db.add(org)
        db.flush()
    return org


def upsert_identity_user(db: Session, identity: Identity) -> User:
    role = settings.oidc_default_role
    if role not in VALID_ROLES:  # config validated at startup; double-check here
        raise SSORejected("invalid_sso_role_configuration")

    user = db.scalar(
        select(User).where(
            User.idp_issuer == identity.issuer, User.idp_subject == identity.subject
        )
    )
    if user is not None and not user.is_active:
        raise SSORejected("account_disabled")

    if user is None and identity.email and identity.email_verified:
        user = db.scalar(select(User).where(User.email == identity.email.lower().strip()))
        if user is not None and not user.is_active:
            raise SSORejected("account_disabled")

    if user is None:
        org = ensure_sso_org(db, settings.oidc_org_name)
        email = (identity.email or f"{identity.subject}@sso.local").lower().strip()
        existing_same_email = db.scalar(select(User).where(User.email == email))
        if existing_same_email is not None:
            # Unverified email collision: never link — isolate in the SSO org
            # under a federation-scoped address instead of taking over the
            # existing account.
            email = f"{identity.subject}@sso.local"
            if db.scalar(select(User).where(User.email == email)):
                raise SSORejected("account_conflict")
        user = User(
            org_id=org.id,
            email=email,
            name=(identity.name or email.split("@", 1)[0])[:160],
            password_hash=None,  # SSO accounts have no local password
            role=role,
            is_active=True,
            idp_issuer=identity.issuer,
            idp_subject=identity.subject,
        )
        db.add(user)
        db.flush()
        return user

    # Existing user: link on first SSO use and keep the profile fresh.
    changed = False
    if user.idp_issuer is None:
        user.idp_issuer, user.idp_subject = identity.issuer, identity.subject
        changed = True
    if identity.name and identity.name != user.name:
        user.name = identity.name[:160]
        changed = True
    if changed:
        db.flush()
    return user
