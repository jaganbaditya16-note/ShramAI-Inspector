"""Local-disk development backend.

Demo-grade: used for local development and tests only. Production must use a
durable private object store (``STORAGE_BACKEND=s3``). Kept behaviourally
identical to the pre-Step-6 implementation so existing workflows are
unaffected.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from pathlib import Path

from .base import (
    DocumentStore,
    InvalidStorageKey,
    MissingObjectError,
    ObjectMeta,
    _checked,
    is_valid_key,
    new_key,
)


class LocalDiskStore(DocumentStore):
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, suffix: str) -> str:
        key = new_key(suffix)
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get_bytes(self, key: str) -> bytes:
        path = self.open_path(key)
        if not path.is_file():
            raise MissingObjectError("Object not found.")
        return path.read_bytes()

    def open_path(self, key: str) -> Path:
        checked = _checked(key)
        path = (self.root / checked).resolve()
        if not str(path).startswith(str(self.root)):
            raise InvalidStorageKey("Storage key escapes storage root.")
        return path

    def delete(self, key: str) -> None:
        if not is_valid_key(key):
            return
        with contextlib.suppress(OSError):
            (self.root / key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        if not is_valid_key(key):
            return False
        return (self.root / key).is_file()

    def stat(self, key: str) -> ObjectMeta | None:
        if not is_valid_key(key):
            return None
        path = self.root / key
        if not path.is_file():
            return None
        file_stat = path.stat()
        return ObjectMeta(
            key=key,
            size_bytes=file_stat.st_size,
            etag=None,
            last_modified=datetime.fromtimestamp(file_stat.st_mtime, tz=UTC),
            content_type=None,
        )
