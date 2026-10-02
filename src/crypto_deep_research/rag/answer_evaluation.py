"""Human-judged evaluation for generated RAG answers and their citations."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CitationJudgment:
    parent_id: str
    supports_claim: bool


@dataclass(frozen=True)
class ClaimJudgment:
    text: str
    supported: bool
    citations: tuple[CitationJudgment, ...]


@dataclass(frozen=True)
class AnswerEvaluationCase:
    query: str
    answer: str
    answer_relevance: int
    retrieved_parent_ids: frozenset[str]
    claims: tuple[ClaimJudgment, ...]
    case_id: str | None = None
    split: str | None = None


def load_answer_cases(path: Path, split: str = "all") -> list[AnswerEvaluationCase]:
    """Load manually reviewed answers, claim support labels, and citation judgments."""
    if split not in {"all", "dev", "test"}:
        raise ValueError("split 'all', 'dev' veya 'test' olmalı")

    cases: list[AnswerEvaluationCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: geçersiz JSON: {exc.msg}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: her satır bir JSON nesnesi olmalı")

        query = row.get("query")
        answer = row.get("answer")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"{path}:{line_number}: query boş olmayan bir metin olmalı")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError(f"{path}:{line_number}: answer boş olmayan bir metin olmalı")

        case_split = row.get("split")
        if case_split is not None and (
            not isinstance(case_split, str) or case_split not in {"dev", "test"}
        ):
            raise ValueError(f"{path}:{line_number}: split 'dev' veya 'test' olmalı")
        if split != "all" and case_split is None:
            raise ValueError(
                f"{path}:{line_number}: --split {split} için her cevapta split alanı gerekli"
            )
        if split != "all" and case_split != split:
            continue

        relevance = row.get("answer_relevance")
        if isinstance(relevance, bool) or not isinstance(relevance, int) or not 1 <= relevance <= 5:
            raise ValueError(f"{path}:{line_number}: answer_relevance 1 ile 5 arasında tamsayı olmalı")
        retrieved = _string_ids(row.get("retrieved_parent_ids"), path, line_number,
                                 "retrieved_parent_ids")
        raw_claims = row.get("claims")
        if not isinstance(raw_claims, list):
            raise ValueError(f"{path}:{line_number}: claims bir liste olmalı")
        claims: list[ClaimJudgment] = []
        for claim_index, raw_claim in enumerate(raw_claims, 1):
            if not isinstance(raw_claim, dict):
                raise ValueError(f"{path}:{line_number}: claims[{claim_index}] nesne olmalı")
            claim_text = raw_claim.get("text")
            supported = raw_claim.get("supported")
            raw_citations = raw_claim.get("citations")
            if not isinstance(claim_text, str) or not claim_text.strip():
                raise ValueError(f"{path}:{line_number}: claims[{claim_index}].text boş olamaz")
            if not isinstance(supported, bool):
                raise ValueError(f"{path}:{line_number}: claims[{claim_index}].supported boolean olmalı")
            if not isinstance(raw_citations, list):
                raise ValueError(f"{path}:{line_number}: claims[{claim_index}].citations liste olmalı")
            citations: list[CitationJudgment] = []
            for citation_index, citation in enumerate(raw_citations, 1):
                if not isinstance(citation, dict):
                    raise ValueError(
                        f"{path}:{line_number}: claims[{claim_index}].citations[{citation_index}] nesne olmalı"
                    )
                parent_id = citation.get("parent_id")
                supports_citation = citation.get("supports_claim")
                if not isinstance(parent_id, str) or not parent_id.strip():
                    raise ValueError(
                        f"{path}:{line_number}: claims[{claim_index}] citation parent_id gerekli"
                    )
                if not isinstance(supports_citation, bool):
                    raise ValueError(
                        f"{path}:{line_number}: claims[{claim_index}] citation supports_claim boolean olmalı"
                    )
                citations.append(CitationJudgment(parent_id.strip(), supports_citation))
            claims.append(ClaimJudgment(claim_text.strip(), supported, tuple(citations)))

        case_id = row.get("id")
        if case_id is not None and not isinstance(case_id, str):
            raise ValueError(f"{path}:{line_number}: id metin olmalı")
        cases.append(
            AnswerEvaluationCase(
                query=query.strip(),
                answer=answer.strip(),
                answer_relevance=relevance,
                retrieved_parent_ids=frozenset(retrieved),
                claims=tuple(claims),
                case_id=case_id.strip() if case_id else None,
                split=case_split,
            )
        )

    if not cases:
        if split == "all":
            raise ValueError(f"{path}: en az bir değerlendirme cevabı gerekli")
        raise ValueError(f"{path}: split '{split}' için etiketli cevap bulunamadı")
    return cases


def _string_ids(value: Any, path: Path, line_number: int, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{path}:{line_number}: {field} metin kimliklerinden oluşan bir liste olmalı")
    return list(dict.fromkeys(item.strip() for item in value))


def _case_metrics(case: AnswerEvaluationCase) -> dict[str, Any]:
    claim_count = len(case.claims)
    supported_count = sum(claim.supported for claim in case.claims)
    cited_claims = [claim for claim in case.claims if claim.citations]
    all_citations = [citation for claim in case.claims for citation in claim.citations]
    grounded_citations = [
        citation
        for citation in all_citations
        if citation.supports_claim and citation.parent_id in case.retrieved_parent_ids
    ]
    claims_with_grounded_citation = sum(
        any(
            citation.supports_claim and citation.parent_id in case.retrieved_parent_ids
            for citation in claim.citations
        )
        for claim in case.claims
    )
    return {
        "n_claims": claim_count,
        "n_supported_claims": supported_count,
        "n_citations": len(all_citations),
        "n_grounded_citations": len(grounded_citations),
        "n_claims_with_grounded_citation": claims_with_grounded_citation,
        "faithfulness": supported_count / claim_count if claim_count else None,
        "citation_coverage": (
            claims_with_grounded_citation / claim_count if claim_count else None
        ),
        "citation_precision": len(grounded_citations) / len(all_citations)
        if all_citations
        else None,
        "answer_relevance": case.answer_relevance,
        "n_claims_with_citations": len(cited_claims),
    }


def evaluate_answers(cases: Sequence[AnswerEvaluationCase]) -> dict[str, Any]:
    """Aggregate human judgments with both query-macro and claim/citation-micro rates."""
    if not cases:
        raise ValueError("en az bir değerlendirme cevabı gerekli")

    per_query: list[dict[str, Any]] = []
    claim_count = supported_count = citation_count = 0
    covered_claim_count = grounded_citation_count = relevance_total = 0
    query_values = {name: [] for name in (
        "faithfulness", "citation_coverage", "citation_precision", "answer_relevance"
    )}
    for index, case in enumerate(cases, 1):
        metrics = _case_metrics(case)
        claim_count += metrics["n_claims"]
        supported_count += metrics["n_supported_claims"]
        citation_count += metrics["n_citations"]
        covered_claim_count += metrics["n_claims_with_grounded_citation"]
        grounded_citation_count += metrics["n_grounded_citations"]
        relevance_total += case.answer_relevance
        for name, value in metrics.items():
            if name in query_values and value is not None:
                query_values[name].append(float(value))
        per_query.append(
            {
                "id": case.case_id or f"a{index}",
                "query": case.query,
                "split": case.split,
                "metrics": metrics,
            }
        )

    macro = {
        name: round(sum(values) / len(values), 6) if values else None
        for name, values in query_values.items()
    }
    micro = {
        "faithfulness": round(supported_count / claim_count, 6) if claim_count else None,
        "citation_coverage": round(covered_claim_count / claim_count, 6)
        if claim_count
        else None,
        "citation_precision": round(grounded_citation_count / citation_count, 6)
        if citation_count
        else None,
        "answer_relevance": round(relevance_total / len(cases), 6),
    }
    return {
        "n_answers": len(cases),
        "n_claims": claim_count,
        "n_citations": citation_count,
        "metrics": {"macro_by_answer": macro, "micro_by_claim_or_citation": micro},
        "answers": per_query,
    }
