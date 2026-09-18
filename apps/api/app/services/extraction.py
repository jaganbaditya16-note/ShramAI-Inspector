from pathlib import Path

def _ocr_image(image) -> str:
    try:
        import pytesseract
        return pytesseract.image_to_string(image).strip()
    except Exception:
        return ""

def _extract_pdf(path: str) -> str:
    pages: list[str] = []
    try:
        from pypdf import PdfReader
        reader = PdfReader(path, strict=False)
        for number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"[Page {number}]\n{text.strip()}")
    except Exception:
        reader = None

    extracted = "\n\n".join(pages).strip()
    if extracted:
        return extracted

    # Scanned/image-only PDFs need rasterization before Tesseract can read them.
    # Limit OCR to the first 20 pages to keep the public demo bounded.
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(path)
        ocr_pages: list[str] = []
        for index, page in enumerate(pdf):
            if index >= 20:
                break
            bitmap = page.render(scale=2, rotation=0)
            image = bitmap.to_pil()
            text = _ocr_image(image)
            if text:
                ocr_pages.append(f"[Page {index + 1} — OCR]\n{text}")
        return "\n\n".join(ocr_pages).strip()
    except Exception:
        return ""

def extract_text(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)

    try:
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            return _ocr_image(image)
    except Exception:
        return ""
