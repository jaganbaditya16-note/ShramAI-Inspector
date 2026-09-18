"""Backend-agnostic storage contract.

Every backend (local disk for development, S3-compatible object storage for
production) implements the same small interface so the application never
depends on local disk directly. Objects are private by default, keys are
always server-generated, and every method validates the key shape first so a
client-supplied value can never traverse paths or escape the bucket/file
root on any backend.
"""

from __future__ import annotations

import contextlib
import re
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class StorageError(Exception):
    """The storage backend failed (unavailable, permissions, network...).

    Never carries key material, credentials or document bytes; callers map it
    to a safe user-facing 503 and log the backend-side detail internally.
    """


class MissingObjectError(StorageError):
    """The object does not exist (deleted, never written, or expired)."""


class InvalidStorageKey(ValueError):
    """The key does not match the server-generated shape (traversal guard)."""


@dataclass(frozen=True)
class ObjectMeta:
    """Safe metadata about a stored object (no credentials, no content)."""

    key: str
    size_bytes: int
    etag: str | None = None
    last_modified: datetime | None = None
    content_type: str | None = None


# Server-generated key shape: YYYY/MM/<32 hex chars><suffix>. Original
# filenames are database metadata, never path components.
_KEY_RE = re.compile(r"^[0-9]{4}/[0-9]{2}/[0-9a-f]{32}\.[a-z0-9]{2,5}$")


def is_valid_key(key: str) -> bool:
    """Keys reaching the store must match the server-generated shape (defends
    against path traversal via any future client-supplied key surface)."""
    return bool(_KEY_RE.match(key))


def new_key(suffix: str) -> str:
    """Generate a fresh, unguessable, traversal-proof storage key."""
    import uuid

    now = datetime.now(UTC)
    return f"{now:%Y/%m}/{uuid.uuid4().hex}{suffix}"


def _checked(key: str) -> str:
    if not is_valid_key(key):
        raise InvalidStorageKey("Invalid storage key.")
    return key


class DocumentStore(ABC):
    """Storage backend contract. Implementations MUST keep objects private
    and MUST NOT accept client-influenced keys."""

    #: True when ``open_path`` returns a temporary file the caller must
    #: release via :meth:`discard_path` (backends that must download first).
    ephemeral_paths: bool = False

    @abstractmethod
    def save(self, data: bytes, suffix: str) -> str:
        """Persist bytes under a fresh server-generated key; return the key."""

    @abstractmethod
    def get_bytes(self, key: str) -> bytes:
        """Return the exact bytes stored under ``key``.

        Raises MissingObjectError when absent, StorageError on backend failure.
        """

    @abstractmethod
    def exists(self, key: str) -> bool:
        """True when the object exists (false when missing, error on failure)."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete the object; deleting a missing object is a no-op."""

    @abstractmethod
    def stat(self, key: str) -> ObjectMeta | None:
        """Metadata for the object, or None when it does not exist."""

    def open_path(self, key: str) -> Path:
        """Materialise the object as a readable local path.

        Base implementation downloads to a private temporary file (used by
        backends without a filesystem); local-disk overrides it with the real
        path. Callers that received a path from an ``ephemeral_paths`` backend
        must call :meth:`discard_path` when done.
        """
        checked = _checked(key)
        data = self.get_bytes(checked)
        handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - handed to caller
            prefix="shramai-store-", delete=False
        )
        with handle:
            handle.write(data)
        return Path(handle.name)

    def discard_path(self, path: Path) -> None:
        """Release a path previously returned by ``open_path`` (base: unlink)."""
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)

    def presign_get(self, key: str, ttl_seconds: int) -> str | None:
        """Short-lived signed GET URL, or None when the backend does not
        support signing (callers then stream through the API instead)."""
        return None
