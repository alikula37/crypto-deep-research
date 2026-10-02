import json

import pytest

from crypto_deep_research.rag.answer_evaluation import evaluate_answers, load_answer_cases


def _answer_row(case_id, split, relevance, claims):
    return {
        "id": case_id,
        "split": split,
        "query": f"query {case_id}",
        "answer": f"answer {case_id}",
        "answer_relevance": relevance,
        "retrieved_parent_ids": ["doc-a"],
        "claims": claims,
    }


def test_answer_metrics_measure_claim_support_and_citation_quality(tmp_path):
    dataset = tmp_path / "answers.jsonl"
    rows = [
        _answer_row(
            "a1",
            "dev",
            4,
            [
                {
                    "text": "supported claim",
                    "supported": True,
                    "citations": [{"parent_id": "doc-a", "supports_claim": True}],
                },
                {
                    "text": "unsupported claim",
                    "supported": False,
                    "citations": [{"parent_id": "doc-outside", "supports_claim": True}],
                },
            ],
        ),
        _answer_row(
            "a2",
            "test",
            5,
            [{"text": "supported but uncited", "supported": True, "citations": []}],
        ),
    ]
    dataset.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    dev = load_answer_cases(dataset, split="dev")
    assert [case.case_id for case in dev] == ["a1"]
    report = evaluate_answers(load_answer_cases(dataset))
    macro = report["metrics"]["macro_by_answer"]
    micro = report["metrics"]["micro_by_claim_or_citation"]

    assert report["n_answers"] == 2
    assert report["n_claims"] == 3
    assert report["n_citations"] == 2
    assert macro["faithfulness"] == 0.75
    assert macro["citation_coverage"] == 0.25
    assert macro["citation_precision"] == 0.5
    assert macro["answer_relevance"] == 4.5
    assert "answer_relevance" not in micro
    assert micro["faithfulness"] == pytest.approx(2 / 3)
    assert micro["citation_coverage"] == pytest.approx(1 / 3)
    assert micro["citation_precision"] == 0.5


def test_answer_without_factual_claims_has_undefined_claim_metrics(tmp_path):
    dataset = tmp_path / "answers.jsonl"
    row = _answer_row("abstain", "test", 2, [])
    dataset.write_text(json.dumps(row), encoding="utf-8")

    metrics = evaluate_answers(load_answer_cases(dataset))["metrics"]
    assert metrics["macro_by_answer"]["faithfulness"] is None
    assert metrics["macro_by_answer"]["citation_coverage"] is None
    assert metrics["macro_by_answer"]["citation_precision"] is None
    assert metrics["macro_by_answer"]["answer_relevance"] == 2.0


def test_answer_evaluator_requires_manual_relevance_and_citation_labels(tmp_path):
    dataset = tmp_path / "answers.jsonl"
    row = _answer_row(
        "bad",
        "dev",
        6,
        [{"text": "claim", "supported": True, "citations": []}],
    )
    dataset.write_text(json.dumps(row), encoding="utf-8")

    with pytest.raises(ValueError, match="answer_relevance 1 ile 5"):
        load_answer_cases(dataset)

    row["answer_relevance"] = 3
    row["claims"][0].pop("supported")
    dataset.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ValueError, match="supported boolean"):
        load_answer_cases(dataset)
