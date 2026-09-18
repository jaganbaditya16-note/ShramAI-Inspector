from pathlib import Path

def extract_text(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(path, strict=False)
            pages = []
            for number, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(f"[Page {number}]\n{text.strip()}")
            return "\n\n".join(pages).strip()
        except Exception:
            return ""

    try:
        import pytesseract
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            text = pytesseract.image_to_string(image)
        return text.strip()
    except Exception:
        return ""
