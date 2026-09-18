"""Administrative endpoints (admin role required).

Currently: on-demand retention sweeps. The startup lifespan also runs a sweep;
this endpoint lets operators trigger one from cron/CI without deploying a
scheduler. Sweeps are bounded and idempotent.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...db.session import get_db
from ...services import retention_service
from ..deps import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/retention/run")
def run_retention(db: Session = Depends(get_db),
                  principal=Depends(require_admin)) -> dict:
    report = retention_service.run_retention_sweep(db)
    return {
        "documents_purged": report.documents_purged,
        "cases_purged": report.cases_purged,
        "sessions_purged": report.sessions_purged,
        "documents_deferred": report.documents_deferred,
        "cases_deferred": report.cases_deferred,
        "skipped_active_jobs": report.skipped_active_jobs,
        "errors": report.errors,
    }
