"""Identity-provider selection (provider-agnostic identity layer).

The authentication *mode* decides how requests resolve a principal
(``deps.get_principal``): ``demo`` injects the virtual demo principal,
``required`` and ``oidc`` both use cookie sessions backed by ``auth_sessions``
rows. The mode additionally decides which identity providers may *create*
sessions:

- ``required``  — password login only (local provider, existing endpoint).
- ``oidc``      — OIDC SSO (+ optional break-glass password login).
- ``demo``      — password login endpoints exist but nothing enforces auth.

This module is the single place that knows which providers are configured;
call sites depend only on :class:`~app.services.identity.base.IdentityProvider`.
"""

from __future__ import annotations

from ...core.config import settings
from .base import Identity, IdentityProvider, LoginChallenge, SSORejected
from .oidc import STATE_COOKIE_NAME, OIDCProvider

__all__ = [
    "STATE_COOKIE_NAME",
    "Identity",
    "IdentityProvider",
    "LoginChallenge",
    "OIDCProvider",
    "SSORejected",
    "get_identity_provider",
    "reset_identity_provider",
]

_provider: IdentityProvider | None = None


def get_identity_provider() -> IdentityProvider | None:
    """The configured SSO provider, or None when SSO is not active."""
    global _provider
    if settings.auth_mode != "oidc":
        return None
    if _provider is None:
        from .oidc import provider_from_settings

        _provider = provider_from_settings()
    return _provider


def reset_identity_provider() -> None:
    """Test helper: drop the cached provider so config changes take effect."""
    global _provider
    _provider = None
