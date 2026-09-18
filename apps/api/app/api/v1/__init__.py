"""API v1 router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from . import audit, auth, cases, dashboard, documents, findings, health, reports

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(cases.router)
api_v1_router.include_router(documents.router)
api_v1_router.include_router(findings.router)
api_v1_router.include_router(reports.router)
api_v1_router.include_router(audit.router)
api_v1_router.include_router(dashboard.router)
