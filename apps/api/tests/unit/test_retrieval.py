"""Retrieval unit tests: provenance, scoring, empty-corpus behaviour."""

from __future__ import annotations

from app.services.retrieval import load_documents, retrieve


def _write_corpus(tmp_path):
    (tmp_path / "wage-reference.md").write_text(
        "---\ntitle: Wage Records Reference\nversion: 2026.1\n---\n"
        "Payslip records should contain gross earnings, net pay, deductions "
        "and the wage period for every worker."
    )
    (tmp_path / "attendance-reference.md").write_text(
        "---\ntitle: Attendance Records Reference\nversion: 2026.1\n---\n"
        "Attendance registers must record present and absent days, working "
        "hours and overtime entries."
    )
    (tmp_path / "_draft.md").write_text("draft material must be ignored")
    return tmp_path


def test_retrieval_scores_and_annotates_provenance(tmp_path):
    corpus = _write_corpus(tmp_path)
    chunks = retrieve("payslip net pay deductions", directory=corpus)
    assert chunks
    top = chunks[0]
    assert top.source == "wage-reference.md"
    assert top.title == "Wage Records Reference"
    assert top.version == "2026.1"
    assert "net pay" in top.content


def test_retrieval_ignores_draft_and_unrelated(tmp_path):
    corpus = _write_corpus(tmp_path)
    assert retrieve("quantum entanglement physics", directory=corpus) == []
    names = [doc.path.name for doc in load_documents(corpus)]
    assert "_draft.md" not in names


def test_retrieval_empty_corpus_returns_empty_list(tmp_path):
    assert retrieve("anything", directory=tmp_path) == []
