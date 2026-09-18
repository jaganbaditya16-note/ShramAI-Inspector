from pathlib import Path
import re

KNOWLEDGE_DIR = Path(__file__).resolve().parents[3] / "data" / "knowledge"

def retrieve(query: str, limit: int = 4) -> list[str]:
    if not query.strip() or not KNOWLEDGE_DIR.exists():
        return []
    tokens = {t for t in re.findall(r"[a-zA-Z]{4,}", query.lower())}
    scored: list[tuple[int, str]] = []
    for path in KNOWLEDGE_DIR.glob("*.md"):
        content = path.read_text(encoding="utf-8", errors="ignore")
        score = sum(1 for token in tokens if token in content.lower())
        if score:
            scored.append((score, f"Source: {path.name}\n{content[:5000]}"))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:limit]]
