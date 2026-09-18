"""Provider-agnostic identity layer.

The application's session/authorisation machinery (opaque cookie tokens,
``auth_sessions`` rows, org-scoped roles, IDOR-safe queries) is intentionally
provider-independent: an *identity provider* only answers "who is this
person?" and the local session is then established the same way for every
provider. This keeps the existing local/demo authentication untouched and
lets enterprise SSO (OIDC today, other protocols later) plug in without
touching authorisation code.

Implementations:
- password login (existing ``/auth/login`` endpoint — local provider).
- ``oidc.OIDCProvider`` — OIDC authorization-code flow with PKCE.

Secrets never enter this package's logs: token/cookie values are excluded
from every log line and error message by design.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class SSORejected(Exception):
    """An SSO login attempt failed validation.

    The message is safe to log internally (categories only — no tokens, no
    provider responses); callers surface a single generic message to users so
    provider internals never leak.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Identity:
    """A verified outside identity (claims validated by the provider)."""

    issuer: str
    subject: str
    email: str | None = None
    email_verified: bool = False
    name: str | None = None
    groups: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class LoginChallenge:
    """What the API needs to start (and later finish) an SSO redirect."""

    authorization_url: str
    cookie_name: str
    cookie_value: str  # signed state bundle (HttpOnly cookie for the browser)
    cookie_max_age: int


class IdentityProvider(ABC):
    """A source of verified identities. Implementations MUST NOT log or
    embed tokens, cookies or client secrets in returned values."""

    name: str = "abstract"

    @abstractmethod
    def begin_login(self) -> LoginChallenge:
        """Create a fresh, single-use login challenge."""

    @abstractmethod
    def complete_login(self, code: str, state: str, cookie_value: str) -> Identity:
        """Validate the callback and return the verified identity.

        ``state`` (query parameter) must match the signed state cookie —
        the CSRF binding for the redirect. Raises SSORejected for any
        validation failure (state mismatch, bad code, unparseable/invalid
        token, wrong audience/issuer/nonce, expiry).
        """
