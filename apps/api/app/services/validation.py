"""Upload validation: extension, declared MIME, magic bytes, size.

Defence in depth for untrusted uploads:
1. Only PDF/PNG/JPEG are accepted (labour documents; bounded parser surface).
2. The declared Content-Type must map to a known extension AND the file must
   start with the expected magic signature — mismatches are rejected.
3. Size is enforced while streaming so memory stays bounded even for hostile
   Content-Length declarations.
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass

from ..core.config import settings
from ..core.errors import PayloadTooLarge, UploadRejected

# content_type -> (set of acceptable extensions, magic prefix)
ALLOWED_TYPES: dict[str, tuple[frozenset[str], bytes]] = {
    "application/pdf": (frozenset({".pdf"}), b"%PDF-"),
    "image/png": (frozenset({".png"}), b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": (frozenset({".jpg", ".jpeg"}), b"\xff\xd8\xff"),
}

_ALLOWED_EXTENSIONS = frozenset({".pdf", ".png", ".jpg", ".jpeg"})
_READ_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str
    suffix: str
    content_type: str
    data: bytes
    size_bytes: int
    sha256: str


def sanitize_filename(raw: str | None) -> str:
    """Return a safe, human-readable basename (never trusted for paths)."""
    name = unicodedata.normalize("NFKC", raw or "document").strip()
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '\r\n\t"<>|:*?')
    name = name.lstrip(".") or "document"
    return name[:255]


def _extension_of(filename: str) -> str:
    dot = filename.rfind(".")
    if dot == -1:
        return ""
    return filename[dot:].lower()


def validate_upload(
    data: bytes, declared_content_type: str | None, raw_filename: str | None
) -> ValidatedUpload:
    filename = sanitize_filename(raw_filename)
    content_type = (declared_content_type or "").split(";")[0].strip().lower()
    suffix = _extension_of(filename)

    if not data:
        raise UploadRejected("The uploaded file is empty.")
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise PayloadTooLarge(f"File exceeds the {settings.max_upload_mb} MB upload limit.")
    if (
        content_type not in ALLOWED_TYPES
        or suffix not in _ALLOWED_EXTENSIONS
    ):
        raise UploadRejected("Unsupported document type. Upload a PDF, PNG or JPEG file.")

    allowed_exts, magic = ALLOWED_TYPES[content_type]
    if suffix not in allowed_exts:
        raise UploadRejected("File extension does not match the declared document type.")
    if not data.startswith(magic):
        raise UploadRejected("File contents do not match the declared document type.")

    # PDFs must contain an end-of-file marker; a truncated header-only file
    # is either corrupt or a parser-abuse probe.
    if content_type == "application/pdf" and (
        b"%%EOF" not in data[-2048:] and b"%%EOF" not in data[:2048]
    ):
        raise UploadRejected("The PDF file appears to be truncated or malformed.")

    return ValidatedUpload(
        filename=filename,
        suffix=".jpg" if suffix == ".jpeg" else suffix,
        content_type=content_type,
        data=data,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


async def read_bounded_upload(file) -> bytes:
    """Read an UploadFile fully but abort early if it exceeds the size cap."""
    max_bytes = settings.max_upload_mb * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise PayloadTooLarge(f"File exceeds the {settings.max_upload_mb} MB upload limit.")
        chunks.append(chunk)
    return b"".join(chunks)
