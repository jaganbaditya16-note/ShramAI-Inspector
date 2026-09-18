from pathlib import Path
import os
import re

def _knowledge_dir() -> Path:
    configured = os.getenv("KNOWLEDGE_DIR", "").strip()
    if configured:
        return Path(configured)

    source = Path(__file__).resolve()
    for parent in source.parents:
        candidate = parent / "data" / "knowledge"
        if candidate.exists():
            return candidate

    # Safe fallback for container images that intentionally do not package
    # the optional legal/reference corpus.
    return source.parent / "knowledge"

KNOWLEDGE_DIR = _knowledge_dir()

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
