"""HTTP middleware: request IDs, access logging, body-size limits, security
headers, default rate limiting and Origin validation for cookie auth."""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..core.config import settings
from ..core.errors import error_envelope
from ..core.logging import get_logger, request_id_var
from ..core.rate_limit import RateLimitRule, limiter

logger = get_logger("shramai.access")

_SAFE_REQUEST_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")

# Paths exempt from the default per-IP bucket (tight buckets exist elsewhere:
# auth and uploads have their own dependency-scoped limits).
RATE_LIMIT_EXEMPT_PATHS = {
    "/", "/api/v1/health", "/api/docs", "/api/redoc", "/api/openapi.json",
}


def _client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a correlation ID to every request and emits one access log line."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        raw_id = request.headers.get("x-request-id", "")
        clean = raw_id if 8 <= len(raw_id) <= 64 and set(raw_id) <= _SAFE_REQUEST_ID_CHARS else ""
        request_id = clean or f"req_{uuid.uuid4().hex[:20]}"
        token = request_id_var.set(request_id)
        request.state.request_id = request_id
        request.state.client_ip = _client_ip(request)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "event=http_request method=%s path=%s status=%s",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "event": "http_request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": request.state.client_ip,
            },
        )
        request_id_var.reset(token)
        return response


class DefaultRateLimitMiddleware(BaseHTTPMiddleware):
    """Per-instance sliding-window limiter for every API route.

    Appropriate for single-instance deployments; multi-instance production
    should enforce limits at the gateway (documented in docs/security)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if settings.rate_limit_enabled and request.url.path not in RATE_LIMIT_EXEMPT_PATHS:
            try:
                limiter.check(
                    RateLimitRule("default", settings.rate_limit_default_per_minute),
                    getattr(request.state, "client_ip", "unknown"),
                )
            except Exception as exc:  # RateLimited -> 429 envelope
                status = getattr(exc, "status_code", 429)
                retry_after = ""
                details = getattr(exc, "details", {}) or {}
                if details.get("retry_after_seconds"):
                    retry_after = str(details["retry_after_seconds"])
                return JSONResponse(
                    status_code=status,
                    content=error_envelope(
                        "rate_limited", "Too many requests. Please retry shortly.",
                        getattr(request.state, "request_id", "-"), details=details or None,
                    ),
                    headers={"Retry-After": retry_after} if retry_after else None,
                )
        return await call_next(request)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Rejects oversized bodies early via Content-Length; streamed bodies are
    additionally bounded while reading the upload."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                declared = int(content_length)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content=error_envelope("bad_request", "Invalid Content-Length header.", "-"),
                )
            limit = settings.max_request_body_mb * 1024 * 1024
            if declared > limit:
                return JSONResponse(
                    status_code=413,
                    content=error_envelope(
                        "payload_too_large",
                        f"Request body exceeds the {settings.max_request_body_mb} MB limit.",
                        getattr(request.state, "request_id", "-"),
                    ),
                )
        return await call_next(request)


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """CSRF defence for cookie sessions: state-changing cross-origin requests
    with cookies are rejected. Same-origin and server-to-server calls (no
    Origin header) pass through."""

    UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        origin = request.headers.get("origin")
        if origin and request.method in self.UNSAFE_METHODS:
            forwarded_host = request.headers.get("x-forwarded-host") if settings.trust_proxy_headers else None
            host = forwarded_host or request.headers.get("host", "")
            origin_host = origin.split("://", 1)[-1]
            # The allow-list may contain full origins ("https://app.example.com")
            # or bare hosts ("app.example.com") — accept either form. (Browser
            # E2E caught that full-origin entries could never match before.)
            allowed = settings.allowed_origin_list
            allowed_hosts = {entry.split("://", 1)[-1] for entry in allowed}
            if (
                origin_host != host
                and origin not in allowed
                and origin_host not in allowed_hosts
            ):
                request_id = getattr(request.state, "request_id", "-")
                return JSONResponse(
                    status_code=403,
                    content=error_envelope("forbidden", "Cross-origin request rejected.", request_id),
                )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cache-Control", "no-store")
        if not settings.is_sqlite or settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response
