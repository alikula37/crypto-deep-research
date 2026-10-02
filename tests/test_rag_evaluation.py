"""Human-judged RAG retrieval metrics are measured at source-document level."""

from types import SimpleNamespace

import pytest

from crypto_deep_research.rag.evaluation import (
    EvaluationCase,
    evaluate_retrieval,
    load_cases,
    retrieval_metrics,
)


def test_retrieval_metrics_count_relevant_parent_documents_once():
    metrics = retrieval_metrics(["doc-a", "doc-b"], {"doc-b", "doc-c"}, k=2)
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["hit_rate"] == 1.0
    assert metrics["mrr"] == 0.5
    assert metrics["ndcg"] == pytest.approx(0.386853)


def test_evaluate_deduplicates_chunks_and_overfetches_sources():
    ranked_chunks = [
        SimpleNamespace(key="a#chunk-0", parent_id="a"),
        SimpleNamespace(key="a#chunk-1", parent_id="a"),
        SimpleNamespace(key="b#chunk-0", parent_id="b"),
    ]
    requested: list[int] = []

    def search(_query, _coin, k):
        requested.append(k)
        return ranked_chunks

    report = evaluate_retrieval(
        search,
        [EvaluationCase("query", frozenset({"b"}))],
        ks=(1, 2),
    )
    assert requested == [8]
    assert report["metrics"]["2"]["recall"] == 1.0
    assert report["queries"][0]["retrieved_parent_ids"] == ["a", "b"]


def test_load_cases_requires_human_relevance_labels(tmp_path):
    dataset = tmp_path / "rag.jsonl"
    dataset.write_text(
        '{"id":"q1","query":" ETF akışları ","coin":" bitcoin ",'
        '"relevant_parent_ids":[" news-abc "]}\n',
        encoding="utf-8",
    )
    case = load_cases(dataset)[0]
    assert case.case_id == "q1"
    assert case.query == "ETF akışları" and case.coin == "bitcoin"
    assert case.relevant_parent_ids == frozenset({"news-abc"})

    dataset.write_text('{"query":"etiketsiz","relevant_parent_ids":[]}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="relevant_parent_ids"):
        load_cases(dataset)
