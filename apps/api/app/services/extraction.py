"""Bounded text extraction for PDFs and images.

Design:
- Digital PDFs: pypdf text layer first, per-page, preserving page boundaries.
- Scanned PDFs: rasterise with pypdfium2 and OCR with Tesseract, bounded by
  page count and scale. OCR is best-effort; failures degrade to a warning,
  never a crash.
- Images: PIL verification then Tesseract OCR when available.
- Output is a normalised full text plus a page map (character offsets per
  page) so every finding can anchor evidence to a page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..core.config import settings
from ..core.errors import ExtractionFailure
from ..core.logging import get_logger

logger = get_logger(__name__)

_OCR_MIN_TEXT_CHARS = 40  # below this a PDF is treated as scanned


@dataclass
class PageText:
    page: int
    text: str
    start: int  # inclusive offset in the normalised full text
    end: int    # exclusive offset in the normalised full text


@dataclass
class ExtractionResult:
    text: str
    pages: list[PageText] = field(default_factory=list)
    page_count: int = 0
    method: str = "none"  # text | ocr | mixed | none
    ocr_available: bool = True
    warnings: list[str] = field(default_factory=list)


_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def _normalize_block(raw: str) -> str:
    """Normalise one page's text while keeping determinism."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _BLANK_LINES_RE.sub("\n\n", text).strip()


def _tesseract_available() -> bool:
    try:
        import shutil

        import pytesseract  # noqa: F401

        return shutil.which("tesseract") is not None
    except Exception:
        return False


def _ocr_image(image) -> str:
    try:
        import pytesseract

        return pytesseract.image_to_string(image) or ""
    except Exception:
        logger.warning("event=ocr_failed image")
        return ""


def _assemble(pages_raw: list[tuple[int, str]], method: str) -> ExtractionResult:
    """Build normalised text + page map from (page_number, raw_text) pairs."""
    parts: list[str] = []
    pages: list[PageText] = []
    cursor = 0
    for number, raw in pages_raw:
        normalized = _normalize_block(raw)
        if not normalized:
            continue
        if parts:
            parts.append("\n\n")
            cursor += 2
        start = cursor
        parts.append(normalized)
        cursor += len(normalized)
        pages.append(PageText(page=number, text=normalized, start=start, end=cursor))
    full = "".join(parts)
    if len(full) > settings.max_extract_chars:
        full = full[: settings.max_extract_chars]
        pages = [p for p in pages if p.start < len(full)]
        for p in pages:
            p.end = min(p.end, len(full))
    return ExtractionResult(
        text=full,
        pages=pages,
        page_count=len(pages_raw) or len(pages),
        method=method,
    )


def _extract_pdf(path: Path, ocr_available: bool) -> ExtractionResult:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path), strict=False)
        page_count = len(reader.pages)
    except (PdfReadError, ValueError, OSError) as exc:
        raise ExtractionFailure("The PDF could not be parsed.") from exc

    if page_count > settings.max_pdf_pages_text:
        raise ExtractionFailure(
            f"The PDF has {page_count} pages; the limit is {settings.max_pdf_pages_text}."
        )

    pages_raw: list[tuple[int, str]] = []
    text_char_total = 0
    for number, page in enumerate(reader.pages[: settings.max_pdf_pages_text], start=1):
        try:
            raw = page.extract_text() or ""
        except Exception:
            logger.warning("event=pdf_page_extract_failed page=%s", number)
            raw = ""
        text_char_total += len(raw.strip())
        pages_raw.append((number, raw))

    result = _assemble(pages_raw, method="text")
    result.page_count = page_count
    if result.text and len(result.text) >= _OCR_MIN_TEXT_CHARS:
        return result

    # Scanned (image-only) PDF: fall back to OCR on the first N pages.
    if not ocr_available:
        result.warnings.append(
            "Little or no embedded text found and OCR is unavailable in this deployment."
        )
        result.method = "none" if not result.text else "text"
        return result

    ocr_pages: list[tuple[int, str]] = []
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        bounded = min(len(pdf), settings.max_pages_ocr)
        for index in range(bounded):
            bitmap = pdf[index].render(scale=settings.ocr_dpi_scale, rotation=0)
            image = bitmap.to_pil()
            ocr_pages.append((index + 1, _ocr_image(image)))
    except Exception:
        logger.exception("event=ocr_fallback_failed")
        result.warnings.append("OCR fallback could not process this PDF.")
        return result

    if ocr_pages:
        ocr_result = _assemble(ocr_pages, method="ocr")
        ocr_result.page_count = page_count
        if result.text:
            # Mixed: keep the small text layer then the OCR text.
            combined = _assemble(
                [(n, t) for n, t in pages_raw] + [(n, f"[OCR]\n{t}") for n, t in ocr_pages],
                method="mixed",
            )
            combined.page_count = page_count
            return combined
        return ocr_result
    result.warnings.append("OCR produced no readable text for this PDF.")
    return result


def _extract_image(path: Path, ocr_available: bool) -> ExtractionResult:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(path) as probe:
            probe.verify()
        with Image.open(path) as image:
            image.load()
            if image.width * image.height > 40_000_000:
                raise ExtractionFailure("Image dimensions exceed the supported limit.")
            if not ocr_available:
                return ExtractionResult(
                    text="", page_count=1, method="none",
                    warnings=["OCR is unavailable in this deployment; image text was not extracted."],
                )
            return _assemble([(1, _ocr_image(image))], method="ocr")
    except UnidentifiedImageError as exc:
        raise ExtractionFailure("The image could not be decoded.") from exc


def extract_document(path: Path) -> ExtractionResult:
    """Extract normalised text with page provenance. Raises ExtractionFailure
    for structurally invalid files; all other problems degrade to warnings."""
    suffix = path.suffix.lower()
    ocr_available = _tesseract_available()
    try:
        if suffix == ".pdf":
            return _extract_pdf(path, ocr_available)
        if suffix in {".png", ".jpg", ".jpeg"}:
            return _extract_image(path, ocr_available)
    except ExtractionFailure:
        raise
    except Exception as exc:
        logger.exception("event=extraction_unexpected_error path=%s", path.name)
        raise ExtractionFailure("Text extraction failed unexpectedly.") from exc
    raise ExtractionFailure("Unsupported file type for extraction.")
