"""Extraction and classification unit tests (no OCR binary required)."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.errors import ExtractionFailure
from app.services.classification import classify
from app.services.extraction import extract_document
from app.services.synthetic import build_synthetic_pdf


def _write(data: bytes, name: str, tmp_path: Path) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_pdf_text_extraction_with_page_map(tmp_path):
    path = _write(build_synthetic_pdf(), "synthetic.pdf", tmp_path)
    result = extract_document(path)
    assert result.method == "text"
    assert result.page_count == 1
    assert "SYNTHETIC DEMO PAYSLIP" in result.text
    assert len(result.pages) == 1
    page = result.pages[0]
    assert page.page == 1
    assert page.start == 0
    assert page.end == len(result.text)


def test_corrupt_pdf_raises_extraction_failure(tmp_path):
    path = _write(b"%PDF-1.4 broken", "broken.pdf", tmp_path)
    with pytest.raises(ExtractionFailure):
        extract_document(path)


def test_image_without_ocr_degrades_with_warning(tmp_path):
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buffer, format="PNG")
    path = _write(buffer.getvalue(), "blank.png", tmp_path)
    result = extract_document(path)
    assert result.method in {"none", "ocr"}  # ocr only when tesseract installed
    if result.method == "none":
        assert result.warnings


def test_classification_payslip():
    text = "Payslip gross salary net pay deductions HRA provident fund pay period"
    result = classify(text)
    assert result.doc_type == "payslip"
    assert result.confidence >= 45


def test_classification_attendance():
    result = classify("Attendance register present absent shift working hours overtime")
    assert result.doc_type == "attendance"


def test_classification_unknown_is_low_confidence():
    result = classify("Random meeting notes about the canteen")
    assert result.doc_type == "unknown"
    assert result.confidence <= 30


def test_classification_empty():
    assert classify("").doc_type == "unknown"
