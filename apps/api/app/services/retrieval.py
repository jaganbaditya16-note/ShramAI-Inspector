"""Retrieval over the approved local knowledge corpus.

The corpus lives in ``data/knowledge/*.md`` with an optional front-matter
header recording source, version and authority (see data/knowledge/README.md).
Retrieval is deterministic token-overlap scoring with title boosting and
provenance in every chunk. The corpus is empty-by-default: the repository
ships only a clearly-marked synthetic sample so retrieval is demonstrable
without fabricating legal sources.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-zA-Z]{4,}")
_STOPWORDS = frozenset({
    "this", "that", "with", "from", "have", "has", "been", "were", "their",
    "which", "shall", "must", "should", "would", "could", "there", "these",
    "those", "then", "than", "them", "they", "such", "also", "into", "over",
    "under", "when", "where", "while", "document", "records", "record",
})
_MAX_SNIPPET_CHARS = 1200


@dataclass(frozen=True)
class KnowledgeChunk:
    source: str
    title: str
    version: str
    content: str
    score: int


@dataclass(frozen=True)
class KnowledgeDocument:
    path: Path
    title: str
    version: str
    body: str
    body_lower: str


def knowledge_dir() -> Path | None:
    configured = settings.knowledge_dir.strip()
    if configured:
        path = Path(configured)
        return path if path.is_dir() else None
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "data" / "knowledge"
        if candidate.is_dir():
            return candidate
    return None


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    meta: dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip().lower()] = value.strip()
    return meta, parts[2]


def load_documents(directory: Path | None = None) -> list[KnowledgeDocument]:
    directory = directory if directory is not None else knowledge_dir()
    if directory is None or not directory.is_dir():
        return []
    docs: list[KnowledgeDocument] = []
    for path in sorted(directory.glob("*.md")):
        if path.name.startswith("_") or path.name.upper().startswith("README"):
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        meta, body = _parse_frontmatter(raw)
        docs.append(
            KnowledgeDocument(
                path=path,
                title=meta.get("title", path.stem.replace("-", " ").title()),
                version=meta.get("version", "unversioned"),
                body=body,
                body_lower=body.lower(),
            )
        )
    return docs


def _retrieve(query: str, limit: int, corpus: list[KnowledgeDocument]) -> list[KnowledgeChunk]:
    tokens = {t for t in _TOKEN_RE.findall(query.lower()) if t not in _STOPWORDS}
    if not tokens:
        return []
    scored: list[KnowledgeChunk] = []
    for doc in corpus:
        title_lower = doc.title.lower()
        score = sum(doc.body_lower.count(token) for token in tokens)
        score += sum(3 for token in tokens if token in title_lower)
        if score <= 0:
            continue
        snippet = doc.body.strip()
        if len(snippet) > _MAX_SNIPPET_CHARS:
            snippet = snippet[:_MAX_SNIPPET_CHARS].rstrip() + "…"
        scored.append(
            KnowledgeChunk(
                source=doc.path.name,
                title=doc.title,
                version=doc.version,
                content=snippet,
                score=score,
            )
        )
    scored.sort(key=lambda chunk: chunk.score, reverse=True)
    return scored[:limit]


def retrieve(
    query: str, limit: int = 3, *, directory: str | os.PathLike | None = None
) -> list[KnowledgeChunk]:
    """Top-k provenance-tagged reference chunks for a query.

    ``directory`` overrides the configured corpus (used by tests); production
    calls always use the configured knowledge directory.
    """
    corpus = load_documents(Path(directory) if directory is not None else None)
    return _retrieve(query, limit, corpus)
