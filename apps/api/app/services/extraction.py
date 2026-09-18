from pathlib import Path


def extract_text(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(path)
            pages = []
            for number, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                pages.append(f"[Page {number}]\\n{text}")
            return "\\n\\n".join(pages).strip()
        except Exception:
            return ""
    try:
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(path))
    except Exception:
        return ""
