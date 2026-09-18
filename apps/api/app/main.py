"""ShramAI Inspector API — application factory.

Wiring order (outermost first):
    RequestContextMiddleware       (request IDs + access logs)
    SecurityHeadersMiddleware      (hardening headers)
    BodySizeLimitMiddleware        (early 413)
    OriginCheckMiddleware          (CSRF defence for cookie sessions)
    CORSMiddleware                 (explicit allow-list only)

Exception handlers map every failure to the consistent error envelope;
unexpected exceptions become a safe 500 with the traceback logged internally.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.v1 import api_v1_router
from .core.config import settings
from .core.errors import AppError, error_envelope
from .core.logging import configure_logging, get_logger, request_id_var
from .core.middleware import (
    BodySizeLimitMiddleware,
    DefaultRateLimitMiddleware,
    OriginCheckMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from .core.security import hash_password, password_policy_error
from .db.session import Base, SessionLocal, engine
from .models import Organization, User
from .services.demo_seed import seed_demo_workspace
from .services.pipeline import recover_interrupted_jobs

logger = get_logger(__name__)

configure_logging(settings.log_level, settings.log_format)


def validate_security_config() -> None:
    """Fail fast on unsafe security configuration (never start in a posture
    that would silently process unscanned documents in production)."""
    if settings.is_production and settings.malware_scan_mode == "off":
        raise RuntimeError(
            "MALWARE_SCAN_MODE=off is forbidden in production. "
            "Configure a clamd scanner (CLAMD_HOST) and set MALWARE_SCAN_MODE=enforcing."
        )
    if settings.malware_scan_mode == "enforcing" and not settings.clamd_host.strip():
        raise RuntimeError("MALWARE_SCAN_MODE=enforcing requires CLAMD_HOST to be configured.")
    if settings.storage_backend == "s3":
        missing = [
            name
            for name, value in (
                ("S3_BUCKET", settings.s3_bucket),
                ("S3_ACCESS_KEY_ID", settings.s3_access_key_id),
                ("S3_SECRET_ACCESS_KEY", settings.s3_secret_access_key),
            )
            if not value.strip()
        ]
        if missing:
            raise RuntimeError(
                f"STORAGE_BACKEND=s3 requires these environment variables: {', '.join(missing)}."
            )
    if settings.is_production and settings.storage_backend == "local":
        raise RuntimeError(
            "STORAGE_BACKEND=local is not production-grade (no durability). "
            "Configure an S3-compatible object store and set STORAGE_BACKEND=s3."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_security_config()
    if settings.effective_auto_create:
        Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        recovered = recover_interrupted_jobs(db)
        if recovered:
            logger.warning("event=startup_recovered_documents count=%d", recovered)
        _bootstrap_admin(db)
        await seed_demo_workspace(db)
    logger.info(
        "event=api_started version=%s env=%s auth_mode=%s pipeline=%s",
        settings.app_version, settings.app_env, settings.auth_mode, settings.pipeline_mode,
    )
    yield
    logger.info("event=api_stopped")


def _bootstrap_admin(db) -> None:
    """Create the first admin when auth_mode=required and no users exist.

    Production requires explicit credentials via environment; non-production
    writes generated credentials to a gitignored local file instead of logs.
    """
    if settings.auth_mode != "required":
        return
    from sqlalchemy import func, select


    user_count = db.scalar(select(func.count(User.id))) or 0
    if user_count:
        return
    email = settings.bootstrap_admin_email.strip().lower()
    password = settings.bootstrap_admin_password
    if settings.is_production and (not email or not password):
        raise RuntimeError(
            "BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD must be set in production."
        )
    if not email:
        email = "admin@shramai.local"
    if password:
        policy_error = password_policy_error(password)
        if policy_error:
            raise RuntimeError(f"Bootstrap admin password rejected: {policy_error}")
    else:
        import secrets
        from pathlib import Path

        password = secrets.token_urlsafe(16)
        cred_file = Path("./bootstrap_admin_credentials.txt")
        cred_file.write_text(
            f"email: {email}\npassword: {password}\n"
            "Change this password after first login. Delete this file afterwards.\n",
            encoding="utf-8",
        )
        logger.warning(
            "event=bootstrap_admin_credentials_written path=%s", str(cred_file.resolve())
        )
    org = Organization(name="Primary Inspectorate", slug="primary")
    db.add(org)
    db.flush()
    db.add(
        User(
            org_id=org.id,
            email=email,
            name=settings.bootstrap_admin_name,
            password_hash=hash_password(password),
            role="admin",
        )
    )
    db.commit()
    logger.info("event=bootstrap_admin_created email=%s", email)


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", request_id_var.get())


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(DefaultRateLimitMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(OriginCheckMiddleware)
if settings.allowed_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

app.include_router(api_v1_router)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"service": settings.app_name, "version": settings.app_version,
            "docs": "/api/docs", "health": "/api/v1/health"}


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    headers = {}
    if exc.status_code == 429 and exc.details.get("retry_after_seconds"):
        headers["Retry-After"] = str(exc.details["retry_after_seconds"])
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(exc.code, exc.message, _rid(request),
                               details=exc.details or None),
        headers=headers or None,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = {
        404: "not_found",
        405: "method_not_allowed",
        401: "unauthorized",
        403: "forbidden",
    }.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else "Request could not be handled."
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(code, message, _rid(request)),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = []
    for error in exc.errors()[:10]:
        details.append({
            "loc": [str(loc) for loc in error.get("loc", [])],
            "msg": error.get("msg", "invalid value"),
            "type": error.get("type", ""),
        })
    return JSONResponse(
        status_code=422,
        content=error_envelope(
            "validation_failed", "Request validation failed.", _rid(request), details=details,
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("event=unhandled_exception path=%s", request.url.path)
    return JSONResponse(
        status_code=500,
        content=error_envelope(
            "internal_error",
            "An unexpected error occurred. Reference this request ID in support requests.",
            _rid(request),
        ),
    )
