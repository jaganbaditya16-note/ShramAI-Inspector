"""Synthetic demo PDF generation test."""

from __future__ import annotations

import io

from app.services.synthetic import build_synthetic_pdf
from pypdf import PdfReader


def test_synthetic_pdf_parses_and_contains_expected_text():
    pdf = build_synthetic_pdf()
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")
    reader = PdfReader(io.BytesIO(pdf), strict=False)
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    assert "SYNTHETIC DEMO PAYSLIP" in text
    assert "EMP-20014" in text
    assert "Gross earnings" in text
