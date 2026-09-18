"""Document storage abstraction.

Backends:
- ``LocalDiskStore`` — development/tests only (demo-grade durability).
- ``S3Store`` — private S3-compatible object storage for production.

The application depends only on the :class:`DocumentStore` contract; the
backend is selected by ``STORAGE_BACKEND`` (see ``app.core.config``) and never
by call sites. Keys are always server-generated and validated against a strict
shape, so no client-supplied value can traverse paths on any backend.
"""

from __future__ import annotations

from ...core.config import settings
from .base import (
    DocumentStore,
    InvalidStorageKey,
    MissingObjectError,
    ObjectMeta,
    StorageError,
    is_valid_key,
)
from .local import LocalDiskStore
from .s3 import S3Store

__all__ = [
    "DocumentStore",
    "InvalidStorageKey",
    "LocalDiskStore",
    "MissingObjectError",
    "ObjectMeta",
    "S3Store",
    "StorageError",
    "get_store",
    "is_valid_key",
    "reset_store",
]

_store: DocumentStore | None = None


def _build_store() -> DocumentStore:
    if settings.storage_backend == "s3":
        return S3Store(
            bucket=settings.s3_bucket,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            session_token=settings.s3_session_token,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            server_side_encryption=settings.s3_server_side_encryption,
        )
    return LocalDiskStore(settings.storage_dir)


def get_store() -> DocumentStore:
    global _store
    if _store is None:
        _store = _build_store()
    return _store


def reset_store() -> None:
    """Test helper: drop the cached backend so config changes take effect."""
    global _store
    _store = None
