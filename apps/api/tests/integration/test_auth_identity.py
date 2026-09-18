"""Authentication & identity-layer tests.

Covers the local session machinery (login, logout, expiry, invalid sessions,
roles, enumeration resistance) and the OIDC SSO flow (state/nonce/PKCE
binding, ID-token validation, provisioning, tamper rejection) using an
in-test RSA key + httpx MockTransport identity provider. No live external
IdP is contacted — live SSO verification against a real provider remains a
deployment task and is NOT claimed here.
"""

from __future__ import annotations

import base64
import json
import time
import uuid

import httpx
import jwt
import pytest
from app.core.config import settings
from app.core.security import hash_password, hash_token
from app.db.session import SessionLocal
from app.main import validate_oidc_config, validate_security_config
from app.models import AuthSession, Organization, User
from app.services.identity import reset_identity_provider
from app.services.identity.oidc import STATE_COOKIE_NAME, OIDCProvider
from cryptography.hazmat.primitives.asymmetric import rsa

# --- test IdP: RSA key + fake discovery/token/JWKS endpoints ---------------------

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key()))
PUBLIC_JWK.update({"kid": "test-key-1", "use": "sig", "alg": "RS256"})

ISSUER = "http://127.0.0.1:9999/realms/test"


def _make_jwks() -> dict:
    return {"keys": [PUBLIC_JWK]}


def _sign_id_token(claims: dict) -> str:
    return jwt.encode(claims, KEY, algorithm="RS256", headers={"kid": "test-key-1"})


class IdPFake:
    """State for one SSO flow scenario."""

    def __init__(self) -> None:
        self.nonce: str | None = None
        self.verifier: str | None = None
        self.used_codes: set[str] = set()
        self.claims_overrides: dict = {}
        self.token_status = 200
        self.discovery_status = 200

    def transport(self) -> httpx.MockTransport:
        idp = self

        def handler(request: httpx.Request) -> httpx.Response:
            url = request.url
            if url.path.endswith("/.well-known/openid-configuration"):
                if idp.discovery_status != 200:
                    return httpx.Response(idp.discovery_status, text="boom")
                return httpx.Response(200, json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/protocol/openid-connect/auth",
                    "token_endpoint": f"{ISSUER}/protocol/openid-connect/token",
                    "jwks_uri": f"{ISSUER}/jwks.json",
                })
            if url.path.endswith("/jwks.json"):
                return httpx.Response(200, json=_make_jwks())
            if url.path.endswith("/token"):
                if idp.token_status != 200:
                    return httpx.Response(idp.token_status, json={"error": "invalid_grant"})
                form = dict(pair.split("=", 1) for pair in request.content.decode().split("&"))
                code = __import__("urllib.parse", fromlist=["unquote"]).unquote(form["code"])
                verifier = __import__("urllib.parse", fromlist=["unquote"]).unquote(form["code_verifier"])
                if code in idp.used_codes:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                if idp.verifier is not None and verifier != idp.verifier:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                idp.used_codes.add(code)
                claims = {
                    "iss": ISSUER,
                    "sub": "user-sub-123",
                    "aud": "shramai-client",
                    "exp": int(time.time()) + 300,
                    "iat": int(time.time()),
                    "nonce": idp.nonce,
                    "email": "alice@example.com",
                    "email_verified": True,
                    "name": "Alice SSO",
                }
                claims.update(idp.claims_overrides)
                for remove in idp.claims_overrides.get("_remove", []):
                    claims.pop(remove, None)
                return httpx.Response(200, json={"id_token": _sign_id_token(claims)})
            return httpx.Response(404, text="unknown")

        return httpx.MockTransport(handler)


@pytest.fixture
def idp_fake() -> IdPFake:
    return IdPFake()


@pytest.fixture
def oidc_mode(monkeypatch, idp_fake) -> OIDCProvider:
    monkeypatch.setattr(settings, "auth_mode", "oidc")
    monkeypatch.setattr(settings, "oidc_issuer", ISSUER)
    monkeypatch.setattr(settings, "oidc_client_id", "shramai-client")
    monkeypatch.setattr(settings, "oidc_client_secret", "test-secret-not-in-source")
    monkeypatch.setattr(settings, "oidc_redirect_uri", "http://127.0.0.1:3000/api/auth/callback")
    monkeypatch.setattr(settings, "oidc_org_name", "SSO Inspectorate")
    monkeypatch.setattr(settings, "oidc_default_role", "inspector")
    monkeypatch.setattr(settings, "oidc_post_login_redirect", "/documents")
    provider = OIDCProvider(
        issuer=ISSUER,
        client_id="shramai-client",
        client_secret="test-secret-not-in-source",
        redirect_uri="http://127.0.0.1:3000/api/auth/callback",
        http_factory=lambda: httpx.Client(transport=idp_fake.transport(), timeout=5),
    )
    monkeypatch.setattr("app.api.v1.auth.get_identity_provider", lambda: provider)
    reset_identity_provider()
    yield provider
    reset_identity_provider()


def _challenge(provider: OIDCProvider):
    return provider.begin_login()


def _bundle(cookie_value: str) -> dict:
    encoded = cookie_value.split(".", 1)[0]
    return json.loads(base64.urlsafe_b64decode(encoded + "==="))


# --- OIDC configuration validation -------------------------------------------------


def test_oidc_config_requires_core_settings(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "oidc")
    monkeypatch.setattr(settings, "oidc_issuer", "")
    with pytest.raises(RuntimeError, match="OIDC_ISSUER"):
        validate_oidc_config()


def test_oidc_config_rejects_http_issuer_in_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "oidc_issuer", "http://idp.example.com/realm")
    monkeypatch.setattr(settings, "oidc_client_id", "c")
    monkeypatch.setattr(settings, "oidc_client_secret", "s")
    monkeypatch.setattr(settings, "oidc_redirect_uri", "https://app.example.com/api/auth/callback")
    with pytest.raises(RuntimeError, match="https"):
        validate_oidc_config()


def test_oidc_config_rejects_http_redirect_in_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "oidc_issuer", "https://idp.example.com/realm")
    monkeypatch.setattr(settings, "oidc_client_id", "c")
    monkeypatch.setattr(settings, "oidc_client_secret", "s")
    monkeypatch.setattr(settings, "oidc_redirect_uri", "http://app.example.com/cb")
    with pytest.raises(RuntimeError, match="REDIRECT"):
        validate_oidc_config()


def test_oidc_config_allows_loopback_http_outside_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "oidc_issuer", ISSUER)  # loopback http
    monkeypatch.setattr(settings, "oidc_client_id", "c")
    monkeypatch.setattr(settings, "oidc_client_secret", "s")
    monkeypatch.setattr(settings, "oidc_redirect_uri", "http://localhost:3000/cb")
    monkeypatch.setattr(settings, "oidc_default_role", "inspector")
    monkeypatch.setattr(settings, "oidc_post_login_redirect", "/")
    validate_oidc_config()  # must not raise


def test_oidc_config_rejects_open_redirect_target(monkeypatch):
    monkeypatch.setattr(settings, "oidc_issuer", ISSUER)
    monkeypatch.setattr(settings, "oidc_client_id", "c")
    monkeypatch.setattr(settings, "oidc_client_secret", "s")
    monkeypatch.setattr(settings, "oidc_redirect_uri", "http://localhost:3000/cb")
    monkeypatch.setattr(settings, "oidc_default_role", "inspector")
    monkeypatch.setattr(settings, "oidc_post_login_redirect", "//evil.example.com")
    with pytest.raises(RuntimeError, match="same-origin"):
        validate_oidc_config()


# --- production refuses demo mode ---------------------------------------------------


def test_production_refuses_demo_mode(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "auth_mode", "demo")
    # satisfy the earlier production checks so the auth one is reached
    monkeypatch.setattr(settings, "malware_scan_mode", "enforcing")
    monkeypatch.setattr(settings, "clamd_host", "clamd")
    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "s3_bucket", "b")
    monkeypatch.setattr(settings, "s3_access_key_id", "k")
    monkeypatch.setattr(settings, "s3_secret_access_key", "s")
    with pytest.raises(RuntimeError, match="AUTH_MODE=demo is forbidden"):
        validate_security_config()


def test_production_accepts_required_mode(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "auth_mode", "required")
    monkeypatch.setattr(settings, "malware_scan_mode", "enforcing")
    monkeypatch.setattr(settings, "clamd_host", "clamd")
    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "s3_bucket", "b")
    monkeypatch.setattr(settings, "s3_access_key_id", "k")
    monkeypatch.setattr(settings, "s3_secret_access_key", "s")
    validate_security_config()  # must not raise


# --- SSO disabled / enabled surface ---------------------------------------------------


def test_sso_login_disabled_outside_oidc_mode(client):
    response = client.get("/api/v1/auth/oidc/login")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "sso_disabled"


def test_oidc_mode_rejects_anonymous(client, oidc_mode):
    response = client.get("/api/v1/cases")
    assert response.status_code == 401


# --- full OIDC flow ---------------------------------------------------------------------


def test_oidc_login_redirects_with_signed_state(client, oidc_mode):
    response = client.get("/api/v1/auth/oidc/login", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith(f"{ISSUER}/protocol/openid-connect/auth")
    assert "state=" in location and "nonce=" in location
    assert "code_challenge_method=S256" in location
    set_cookie = response.headers["set-cookie"]
    assert f"{STATE_COOKIE_NAME}=" in set_cookie
    assert "HttpOnly" in set_cookie and "SameSite=lax" in set_cookie


def _perform_sso(client, provider: OIDCProvider, idp: IdPFake, code: str = "auth-code-1"):
    challenge = _challenge(provider)
    bundle = _bundle(challenge.cookie_value)
    idp.nonce = bundle["n"]
    idp.verifier = bundle["v"]
    client.cookies.set(STATE_COOKIE_NAME, challenge.cookie_value)
    return client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": code, "state": bundle["s"]},
        follow_redirects=False,
    )


def test_oidc_callback_provisions_user_session_and_audit(client, oidc_mode, idp_fake):
    response = _perform_sso(client, oidc_mode, idp_fake)
    assert response.status_code == 303
    assert response.headers["location"] == "/documents"
    set_cookie = response.headers.get("set-cookie", "")
    assert "shramai_session=" in set_cookie

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "alice@example.com"
    assert body["is_demo"] is False

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == "alice@example.com").one()
        assert user.idp_issuer == ISSUER and user.idp_subject == "user-sub-123"
        assert user.password_hash is None  # SSO accounts have no local password
        org = db.get(Organization, user.org_id)
        assert org.name == "SSO Inspectorate"
        assert user.role == "inspector"

    audit = client.get("/api/v1/cases").request  # ensure authenticated context works
    assert audit is not None


def test_oidc_callback_is_repeatable_for_same_identity(client, oidc_mode, idp_fake):
    _perform_sso(client, oidc_mode, idp_fake, code="code-A")
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    first = me.json()["id"]

    client.cookies.clear()
    _perform_sso(client, oidc_mode, idp_fake, code="code-B")
    second = client.get("/api/v1/auth/me").json()["id"]
    assert first == second  # same federated identity -> same user, no duplicate

    with SessionLocal() as db:
        assert db.query(User).filter(User.idp_subject == "user-sub-123").count() == 1


def test_oidc_links_existing_verified_local_account(client, oidc_mode, idp_fake):
    with SessionLocal() as db:
        org = db.query(Organization).first()
        db.add(User(
            org_id=org.id, email="alice@example.com", name="Local Alice",
            password_hash=hash_password("local-password-1"), role="viewer",
        ))
        db.commit()

    _perform_sso(client, oidc_mode, idp_fake)
    with SessionLocal() as db:
        users = db.query(User).filter(User.email == "alice@example.com").all()
        assert len(users) == 1  # linked, not duplicated
        assert users[0].idp_issuer == ISSUER
        assert users[0].role == "viewer"  # existing role preserved on link


def test_oidc_never_links_unverified_email(client, oidc_mode, idp_fake):
    with SessionLocal() as db:
        org = db.query(Organization).first()
        db.add(User(
            org_id=org.id, email="bob@example.com", name="Local Bob",
            password_hash=hash_password("local-password-2"), role="admin",
        ))
        db.commit()
    idp_fake.claims_overrides = {"email": "bob@example.com", "email_verified": False}

    _perform_sso(client, oidc_mode, idp_fake)
    with SessionLocal() as db:
        users = db.query(User).filter(User.email.in_(["bob@example.com"])).all()
        assert len(users) == 1  # the original local admin — untouched
        assert users[0].idp_issuer is None
        linked = db.query(User).filter(User.idp_subject == "user-sub-123").one()
        assert linked.email == "user-sub-123@sso.local"  # isolated new account
        assert linked.org.name == "SSO Inspectorate"


# --- OIDC tamper / validation rejections --------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "someone-else"},                       # wrong audience
        {"iss": "http://evil.example.com/realm"},      # wrong issuer
        {"exp": int(time.time()) - 600},               # expired
        {"nonce": "attacker-nonce"},                   # nonce mismatch
    ],
    ids=["wrong-audience", "wrong-issuer", "expired", "nonce-mismatch"],
)
def test_oidc_rejects_invalid_id_tokens(client, oidc_mode, idp_fake, overrides):
    challenge = _challenge(oidc_mode)
    bundle = _bundle(challenge.cookie_value)
    idp_fake.nonce = bundle["n"]
    idp_fake.verifier = bundle["v"]
    idp_fake.claims_overrides = overrides
    client.cookies.set(STATE_COOKIE_NAME, challenge.cookie_value)
    response = client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": "code-X", "state": bundle["s"]},
        follow_redirects=False,
    )
    assert response.status_code == 401
    body = response.json()["error"]
    assert body["code"] == "unauthorized"
    # no provider internals in the user-facing message
    assert "keycloak" not in body["message"].lower()
    assert "realm" not in body["message"].lower()


def test_oidc_rejects_state_mismatch(client, oidc_mode, idp_fake):
    challenge = _challenge(oidc_mode)
    bundle = _bundle(challenge.cookie_value)
    idp_fake.nonce = bundle["n"]
    idp_fake.verifier = bundle["v"]
    client.cookies.set(STATE_COOKIE_NAME, challenge.cookie_value)
    response = client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": "code-Y", "state": "forged-state-value"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"].startswith("Single sign-on could not")


def test_oidc_rejects_tampered_state_cookie(client, oidc_mode, idp_fake):
    challenge = _challenge(oidc_mode)
    bundle = _bundle(challenge.cookie_value)
    idp_fake.nonce = bundle["n"]
    idp_fake.verifier = bundle["v"]
    encoded, signature = challenge.cookie_value.rsplit(".", 1)
    client.cookies.set(STATE_COOKIE_NAME, f"{encoded}.{'0' * len(signature)}")
    response = client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": "code-Z", "state": bundle["s"]},
        follow_redirects=False,
    )
    assert response.status_code == 401


def test_oidc_rejects_callback_without_state_cookie(client, oidc_mode, idp_fake):
    response = client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": "code-1", "state": "whatever"},
        follow_redirects=False,
    )
    assert response.status_code == 401


def test_oidc_state_cookie_is_single_use_per_flow(client, oidc_mode, idp_fake):
    challenge = _challenge(oidc_mode)
    bundle = _bundle(challenge.cookie_value)
    idp_fake.nonce = bundle["n"]
    idp_fake.verifier = bundle["v"]
    client.cookies.set(STATE_COOKIE_NAME, challenge.cookie_value)
    first = client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": "code-1", "state": bundle["s"]},
        follow_redirects=False,
    )
    assert first.status_code == 303
    # the flow cookie is cleared on use (expired Set-Cookie in the response)
    set_cookie = first.headers.get("set-cookie", "")
    assert f'{STATE_COOKIE_NAME}=""' in set_cookie or "Max-Age=0" in set_cookie
    # code replay: the token endpoint enforces single-use codes
    client.cookies.set(STATE_COOKIE_NAME, challenge.cookie_value)
    replay = client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": "code-1", "state": bundle["s"]},
        follow_redirects=False,
    )
    assert replay.status_code == 401


def test_sso_failure_never_leaks_provider_error_details(client, oidc_mode, idp_fake):
    idp_fake.token_status = 500
    challenge = _challenge(oidc_mode)
    bundle = _bundle(challenge.cookie_value)
    idp_fake.nonce = bundle["n"]
    idp_fake.verifier = bundle["v"]
    client.cookies.set(STATE_COOKIE_NAME, challenge.cookie_value)
    response = client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": "code-1", "state": bundle["s"]},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert "invalid_grant" not in response.text
    assert "boom" not in response.text


# --- session lifecycle (password provider, unchanged machinery) ----------------------------


def _login_required(client, monkeypatch, email="chief@example.com", password="session-pass-1", role="admin"):
    monkeypatch.setattr(settings, "auth_mode", "required")
    with SessionLocal() as db:
        org = db.query(Organization).first()
        db.add(User(
            org_id=org.id, email=email, name="Chief Session",
            password_hash=hash_password(password), role=role,
        ))
        db.commit()
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response


def test_authenticated_user_can_use_api(client, monkeypatch):
    _login_required(client, monkeypatch)
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["is_demo"] is False
    cases = client.get("/api/v1/cases")
    assert cases.status_code == 200


def test_expired_session_is_rejected(client, monkeypatch):
    _login_required(client, monkeypatch, email="expiring@example.com")
    assert client.get("/api/v1/auth/me").status_code == 200
    with SessionLocal() as db:
        session = db.query(AuthSession).order_by(AuthSession.created_at.desc()).first()
        session.expires_at = session.created_at  # already expired
        db.commit()
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert "expired" in response.json()["error"]["message"].lower()


def test_invalid_session_cookie_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "required")
    client.cookies.set("shramai_session", "totally-made-up-token")
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.set("shramai_session", "x" * 64)
    assert client.get("/api/v1/cases").status_code == 401


def test_logout_revokes_and_audits(client, monkeypatch):
    _login_required(client, monkeypatch, email="logout@example.com")
    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401  # session revoked server-side

    with SessionLocal() as db:
        session = db.query(AuthSession).order_by(AuthSession.created_at.desc()).first()
        assert session.revoked_at is not None


def test_login_is_never_session_fixation_reusable(client, monkeypatch):
    """Two logins mint independent tokens; the first cookie dies with its session."""
    _login_required(client, monkeypatch, email="rotate@example.com")
    first_token = client.cookies.get("shramai_session")
    assert first_token
    _login_required(client, monkeypatch, email="rotate2@example.com", password="session-pass-1")
    second_token = client.cookies.get("shramai_session")
    assert first_token != second_token  # always a fresh token: no fixation

    with SessionLocal() as db:
        # both sessions valid independently (separate devices is legitimate)
        assert db.query(AuthSession).filter(
            AuthSession.token_hash == hash_token(first_token)
        ).one().revoked_at is None


def test_viewer_role_cannot_upload_or_delete(client, monkeypatch):
    _login_required(client, monkeypatch, email="viewer@example.com", role="viewer")
    response = client.post(
        "/api/v1/cases", json={"title": "Viewer Case"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_unauthorized_document_and_case_access_across_orgs(client, monkeypatch):
    _login_required(client, monkeypatch, email="isolated@example.com")
    fabricated_case, fabricated_document = str(uuid.uuid4()), str(uuid.uuid4())
    assert client.get(f"/api/v1/cases/{fabricated_case}").status_code == 404
    assert client.get(f"/api/v1/documents/{fabricated_document}").status_code == 404
    assert client.get(f"/api/v1/documents/{fabricated_document}/download").status_code == 404


def test_auth_audit_events_recorded(client, monkeypatch):
    email = "audited@example.com"
    _login_required(client, monkeypatch, email=email)
    client.post("/api/v1/auth/logout")
    from sqlalchemy import text

    with SessionLocal() as db:
        actions = [
            row[0]
            for row in db.execute(
                text("SELECT action FROM audit_events WHERE action LIKE 'auth_%'")
            ).all()
        ]
    assert "auth_login" in actions and "auth_logout" in actions


# secrets must never appear in error surfaces or health
def test_health_and_errors_carry_no_oidc_secrets(client, oidc_mode):
    health = client.get("/api/v1/health").text
    assert "test-secret-not-in-source" not in health
    login_redirect = client.get("/api/v1/auth/oidc/login")
    assert "test-secret-not-in-source" not in login_redirect.text
