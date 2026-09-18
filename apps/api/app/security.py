from fastapi import Header, HTTPException, Request
from .core.config import settings

PUBLIC_PATHS = {
    "/api/v1/health",
    "/api/docs",
    "/api/openapi.json",
    "/api/redoc",
}

def require_demo_token(request: Request, authorization: str | None = Header(default=None)):
    configured = getattr(settings, "demo_auth_token", "")
    if not configured or request.url.path in PUBLIC_PATHS:
        return
    if authorization != f"Bearer {configured}":
        raise HTTPException(status_code=401, detail="Authentication required")
