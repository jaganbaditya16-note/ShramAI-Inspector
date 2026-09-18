from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from ..core.config import settings

ALLOWED = {
    "application/pdf": (".pdf", b"%PDF-"),
    "image/png": (".png", b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": (".jpg", b"\xff\xd8\xff"),
}

async def save_upload(file: UploadFile) -> tuple[str, int]:
    original = Path(file.filename or "").name
    suffix = Path(original).suffix.lower()
    content_type = file.content_type or ""
    if content_type not in ALLOWED or suffix not in {".pdf", ".png", ".jpg", ".jpeg"}:
        raise HTTPException(400, "Unsupported document type. Use PDF, PNG or JPEG.")
    if content_type == "image/jpeg" and suffix == ".jpeg":
        suffix = ".jpg"

    data = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(data) == 0:
        raise HTTPException(400, "Empty document is not allowed.")
    if len(data) > max_bytes:
        raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB limit.")

    magic = ALLOWED[content_type][1]
    if not data.startswith(magic):
        raise HTTPException(400, "File signature does not match its declared type.")

    directory = Path(settings.upload_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid4().hex}{suffix}"
    path.write_bytes(data)
    return str(path), len(data)
