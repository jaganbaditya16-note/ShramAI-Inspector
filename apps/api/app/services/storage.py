"""Document storage abstraction.

The protocol exists so production can swap in durable private object storage
(S3/GCS with SSE-KMS) without touching the pipeline. The local implementation
is for development/demo only and stores files under server-generated UUID
keys — original filenames are metadata, never path components.
"""

from __future__ import annotations

import contextlib
import re
from abc import ABC, abstractmethod
from datetime import UTC
from pathlib import Path

from ..core.config import settings


class DocumentStore(ABC):
    @abstractmethod
    def save(self, data: bytes, suffix: str) -> str:
        """Persist bytes, return a storage key."""

    @abstractmethod
    def open_path(self, key: str) -> Path:
        """Resolve a key to a readable local path (local backend)."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete the object at key (best effort)."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...


_KEY_RE = re.compile(r"^[0-9]{4}/[0-9]{2}/[0-9a-f]{32}\.[a-z0-9]{2,5}$")


def is_valid_key(key: str) -> bool:
    """Keys reaching the store must match the server-generated shape (defends
    against path traversal via any future client-supplied key surface)."""
    return bool(_KEY_RE.match(key))


class LocalDiskStore(DocumentStore):
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, suffix: str) -> str:
        import uuid
        from datetime import datetime

        now = datetime.now(UTC)
        key = f"{now:%Y/%m}/{uuid.uuid4().hex}{suffix}"
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def open_path(self, key: str) -> Path:
        if not is_valid_key(key):
            raise ValueError("Invalid storage key.")
        path = (self.root / key).resolve()
        if not str(path).startswith(str(self.root)):
            raise ValueError("Storage key escapes storage root.")
        return path

    def delete(self, key: str) -> None:
        if not is_valid_key(key):
            return
        path = self.root / key
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        if not is_valid_key(key):
            return False
        return (self.root / key).is_file()


_store: DocumentStore | None = None


def get_store() -> DocumentStore:
    global _store
    if _store is None:
        _store = LocalDiskStore(settings.storage_dir)
    return _store


def reset_store() -> None:
    """Test helper."""
    global _store
    _store = None
