"""Health and readiness."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.config import settings
from ...db.session import database_alive, get_db
from ...services.ai import get_provider
from ...services.malware import get_scanner

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    provider = get_provider()
    return {
        "status": "ok" if database_alive(db) else "degraded",
        "version": settings.app_version,
        "app_env": settings.app_env,
        "auth_mode": settings.auth_mode,
        "ai": {
            "provider": provider.name,
            "configured": provider.name != "disabled",
        },
        "malware": {
            "mode": settings.malware_scan_mode,
            "engine": get_scanner().name if get_scanner() else None,
            "configured": get_scanner() is not None,
        },
    }
