"""Upload validation and storage key safety."""

from __future__ import annotations

import pytest
from app.core.config import settings
from app.core.errors import PayloadTooLarge, UploadRejected
from app.services.storage import LocalDiskStore, is_valid_key
from app.services.synthetic import build_synthetic_pdf
from app.services.validation import sanitize_filename, validate_upload

PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"x" * 64
JPEG_MAGIC = b"\xff\xd8\xff" + b"e" * 64


def test_valid_pdf_passes():
    pdf = build_synthetic_pdf()
    result = validate_upload(pdf, "application/pdf", "records/payslip june.pdf")
    assert result.suffix == ".pdf"
    assert result.filename == "payslip june.pdf"
    assert len(result.sha256) == 64


def test_rejects_fake_pdf_magic():
    with pytest.raises(UploadRejected):
        validate_upload(b"not a pdf at all %%EOF", "application/pdf", "fake.pdf")


def test_rejects_truncated_pdf():
    with pytest.raises(UploadRejected):
        validate_upload(b"%PDF-1.4 no eof marker", "application/pdf", "trunc.pdf")


def test_rejects_extension_mime_mismatch():
    with pytest.raises(UploadRejected):
        validate_upload(PNG_MAGIC, "image/png", "image.pdf")


def test_rejects_unknown_content_type():
    with pytest.raises(UploadRejected):
        validate_upload(b"MZ\x90\x00", "application/x-msdownload", "evil.exe")


def test_rejects_missing_extension():
    with pytest.raises(UploadRejected):
        validate_upload(PNG_MAGIC, "image/png", "noext")


def test_rejects_empty_upload():
    with pytest.raises(UploadRejected):
        validate_upload(b"", "application/pdf", "empty.pdf")


def test_rejects_oversize(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    big = b"%PDF-1.4\n" + b"a" * (1024 * 1024 + 1) + b"\n%%EOF"
    with pytest.raises(PayloadTooLarge):
        validate_upload(big, "application/pdf", "big.pdf")


def test_jpeg_extension_normalised():
    result = validate_upload(JPEG_MAGIC, "image/jpeg", "scan.jpeg")
    assert result.suffix == ".jpg"


def test_sanitize_filename_strips_paths_and_controls():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("a\x00b\n(c).pdf") == "ab(c).pdf"
    assert sanitize_filename(None) == "document"
    assert sanitize_filename("....") == "document"


def test_storage_key_shape_and_traversal_guard(tmp_path):
    store = LocalDiskStore(str(tmp_path / "store"))
    key = store.save(b"data", ".pdf")
    assert is_valid_key(key)
    assert not is_valid_key("../escape.pdf")
    assert not is_valid_key("2026/09/../../etc/passwd.pdf")
    resolved = store.open_path(key)
    assert resolved.is_file()
    with pytest.raises(ValueError):
        store.open_path("../escape.pdf")
