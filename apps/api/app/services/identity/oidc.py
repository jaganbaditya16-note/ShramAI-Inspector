"""OIDC identity provider (authorization-code flow + PKCE, confidential client).

Works with any spec-compliant provider (Keycloak, Entra ID, Okta, Google,
Auth0, ...). Security properties implemented here:

- **Discovery** via ``/.well-known/openid-configuration``; the discovered
  ``issuer`` must equal the configured issuer (exact match) before any
  endpoint from the document is used.
- **State + nonce + PKCE**: every login generates a random ``state``, a random
  ``nonce`` and an S256 PKCE verifier. All three travel to the browser only
  inside a signed, HttpOnly, short-lived cookie (HMAC-SHA256, 5-minute expiry);
  the callback recomputes the HMAC with constant-time comparison and the
  cookie is deleted on use.
- **Code exchange** happens server-side only; client secrets never reach the
  browser.
- **ID-token validation**: signature against the provider's JWKS (``kid``
  match, RS256 family), exact ``iss`` match, ``aud`` must contain the client
  id, ``exp``/``iat`` honoured with a small leeway, and the ``nonce`` claim
  must equal the challenge nonce.
- **No secrets in logs**: log lines carry event categories only; token and
  cookie values never enter log records, error messages or exceptions that
  reach users.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from ...core.config import settings
from .base import Identity, IdentityProvider, LoginChallenge, SSORejected

logger = logging.getLogger("shramai.identity")

STATE_COOKIE_NAME = "shramai_oidc_state"
_STATE_TTL_SECONDS = 300
_DISCOVERY_CACHE_TTL = 600
_SIGNED_ALGS = {"RS256", "RS384", "RS512", "ES256"}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(48))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


class OIDCProvider(IdentityProvider):
    name = "oidc"

    def __init__(
        self,
        *,
        issuer: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: str = "openid email profile",
        state_secret: str = "",
        timeout: float = 10.0,
        leeway: int = 60,
        http_factory: Any | None = None,
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self._client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        self.timeout = timeout
        self.leeway = leeway
        key_material = state_secret or client_secret
        self._state_key = hashlib.sha256(
            b"shramai-oidc-state|" + key_material.encode("utf-8")
        ).digest()
        # Injectable for tests; production uses real HTTP with bounded timeouts.
        self._http_factory = http_factory or (
            lambda: httpx.Client(timeout=self.timeout, follow_redirects=False)
        )
        self._discovery: dict[str, Any] | None = None
        self._discovery_fetched_at: float = 0.0
        self._jwks: dict[str, Any] | None = None

    def __repr__(self) -> str:  # client secret never leaks
        return f"<OIDCProvider issuer={self.issuer!r} client_id={self.client_id!r}>"

    # --- HTTP plumbing ------------------------------------------------------------

    def _get_json(self, url: str) -> dict[str, Any]:
        with self._http_factory() as client:
            response = client.get(url, headers={"Accept": "application/json"})
        if response.status_code != 200:
            logger.error("event=sso_discovery_failed status=%d", response.status_code)
            raise SSORejected("identity_provider_unreachable")
        try:
            return response.json()
        except ValueError as exc:
            raise SSORejected("identity_provider_invalid_response") from exc

    def _well_known(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._discovery is not None and now - self._discovery_fetched_at < _DISCOVERY_CACHE_TTL:
            return self._discovery
        document = self._get_json(f"{self.issuer}/.well-known/openid-configuration")
        if document.get("issuer", "").rstrip("/") != self.issuer:
            # Discovery mismatch = misconfiguration or interception attempt.
            logger.error("event=sso_issuer_mismatch")
            raise SSORejected("identity_provider_issuer_mismatch")
        for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            if not document.get(field):
                logger.error("event=sso_discovery_incomplete field=%s", field)
                raise SSORejected("identity_provider_invalid_response")
        self._discovery = document
        self._discovery_fetched_at = now
        return document

    def _jwks_for(self, kid: str) -> dict[str, Any]:
        if self._jwks is not None and any(k.get("kid") == kid for k in self._jwks.get("keys", [])):
            return self._jwks
        jwks = self._get_json(str(self._well_known()["jwks_uri"]))
        if not isinstance(jwks.get("keys"), list):
            raise SSORejected("identity_provider_invalid_response")
        self._jwks = jwks
        return self._jwks

    # --- challenge ------------------------------------------------------------------

    def begin_login(self) -> LoginChallenge:
        discovery = self._well_known()
        state = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(24)
        verifier, challenge = _pkce_pair()
        query = urlencode({
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
        url = f"{discovery['authorization_endpoint']}?{query}"
        return LoginChallenge(
            authorization_url=url,
            cookie_name=STATE_COOKIE_NAME,
            cookie_value=self._sign_bundle({"s": state, "n": nonce, "v": verifier}),
            cookie_max_age=_STATE_TTL_SECONDS,
        )

    # --- callback ---------------------------------------------------------------------

    def complete_login(self, code: str, state: str, cookie_value: str) -> Identity:
        bundle = self._verify_bundle(cookie_value)
        if not hmac.compare_digest(str(bundle["s"]), state):
            # Query state ≠ cookie state: the redirect did not originate from
            # this browser's login attempt (CSRF defence).
            logger.warning("event=sso_state_mismatch")
            raise SSORejected("state_mismatch")
        claims = self._exchange_and_verify(code, bundle["n"], bundle["v"])
        return Identity(
            issuer=str(claims["iss"]),
            subject=str(claims["sub"]),
            email=claims.get("email"),
            email_verified=bool(claims.get("email_verified", False)),
            name=claims.get("name") or claims.get("preferred_username"),
            groups=tuple(claims.get("groups", ()) or ()),
        )

    def _exchange_and_verify(self, code: str, nonce: str, verifier: str) -> dict[str, Any]:
        discovery = self._well_known()
        with self._http_factory() as client:
            response = client.post(
                str(discovery["token_endpoint"]),
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "code_verifier": verifier,
                    "client_id": self.client_id,
                    "client_secret": self._client_secret,
                },
                headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            )
        if response.status_code != 200:
            # The provider's body is never echoed (it can contain internals).
            logger.warning("event=sso_token_exchange_failed status=%d", response.status_code)
            raise SSORejected("code_exchange_rejected")
        try:
            id_token = str(response.json()["id_token"])
        except (ValueError, KeyError) as exc:
            raise SSORejected("identity_provider_invalid_response") from exc
        return self._verify_id_token(id_token, nonce)

    def _verify_id_token(self, token: str, nonce: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise SSORejected("malformed_id_token") from exc
        alg = str(header.get("alg", ""))
        kid = str(header.get("kid", ""))
        if alg not in _SIGNED_ALGS or not kid:
            logger.warning("event=sso_id_token_unsupported_alg alg=%s", alg or "none")
            raise SSORejected("malformed_id_token")
        jwk = next((k for k in self._jwks_for(kid).get("keys", []) if k.get("kid") == kid), None)
        if jwk is None:
            raise SSORejected("malformed_id_token")
        try:
            key = jwt.PyJWK.from_dict(jwk).key
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,
                algorithms=[alg],
                audience=self.client_id,
                issuer=self.issuer,
                leeway=self.leeway,
                options={"require": ["exp", "iat", "iss", "sub", "aud", "nonce"]},
            )
        except jwt.InvalidSignatureError:
            logger.warning("event=sso_id_token_bad_signature")
            raise SSORejected("invalid_id_token") from None
        except jwt.ExpiredSignatureError:
            raise SSORejected("expired_id_token") from None
        except jwt.InvalidTokenError:
            raise SSORejected("invalid_id_token") from None
        if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
            logger.warning("event=sso_nonce_mismatch")
            raise SSORejected("nonce_mismatch")
        return claims

    # --- signed state bundle ------------------------------------------------------------

    def _sign_bundle(self, payload: dict[str, Any]) -> str:
        body = dict(payload)
        body["e"] = int(time.time()) + _STATE_TTL_SECONDS
        encoded = _b64url(json.dumps(body, separators=(",", ":")).encode("utf-8"))
        signature = hmac.new(self._state_key, encoded.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{encoded}.{signature}"

    def _verify_bundle(self, cookie_value: str) -> dict[str, Any]:
        try:
            encoded, signature = cookie_value.rsplit(".", 1)
        except ValueError as exc:
            raise SSORejected("invalid_state") from exc
        expected = hmac.new(self._state_key, encoded.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            logger.warning("event=sso_state_signature_invalid")
            raise SSORejected("invalid_state")
        try:
            body = json.loads(base64.urlsafe_b64decode(encoded + "==="))
        except (ValueError, TypeError) as exc:
            raise SSORejected("invalid_state") from exc
        if not isinstance(body, dict) or int(body.get("e", 0)) < int(time.time()):
            logger.warning("event=sso_state_expired")
            raise SSORejected("state_expired")
        if not body.get("s") or not body.get("n") or not body.get("v"):
            raise SSORejected("invalid_state")
        return body


@dataclass
class _OIDCConfigSnapshot:
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: str
    state_secret: str
    timeout: float
    leeway: int


def provider_from_settings() -> OIDCProvider:
    """Build the configured provider (settings snapshot bound at construction)."""
    snapshot = _OIDCConfigSnapshot(
        issuer=settings.oidc_issuer,
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        redirect_uri=settings.oidc_redirect_uri,
        scopes=settings.oidc_scopes,
        state_secret=settings.oidc_state_secret,
        timeout=settings.oidc_http_timeout_seconds,
        leeway=settings.oidc_token_leeway_seconds,
    )
    return OIDCProvider(
        issuer=snapshot.issuer,
        client_id=snapshot.client_id,
        client_secret=snapshot.client_secret,
        redirect_uri=snapshot.redirect_uri,
        scopes=snapshot.scopes,
        state_secret=snapshot.state_secret,
        timeout=snapshot.timeout,
        leeway=snapshot.leeway,
    )
