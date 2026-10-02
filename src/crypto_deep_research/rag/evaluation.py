"""Offline, human-judged evaluation for RAG retrieval quality."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvaluationCase:
    query: str
    relevant_parent_ids: frozenset[str]
    coin: str | None = None
    case_id: str | None = None


def load_cases(path: Path) -> list[EvaluationCase]:
    """Load JSONL queries whose relevance labels are source-document IDs."""
    cases: list[EvaluationCase] = []
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
        relevant = row.get("relevant_parent_ids")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"{path}:{line_number}: query boş olmayan bir metin olmalı")
        if not isinstance(relevant, list) or not relevant or not all(
            isinstance(item, str) and item.strip() for item in relevant
        ):
            raise ValueError(
                f"{path}:{line_number}: relevant_parent_ids en az bir belge ID'si içermeli"
            )
        coin = row.get("coin")
        case_id = row.get("id")
        if coin is not None and not isinstance(coin, str):
            raise ValueError(f"{path}:{line_number}: coin metin olmalı")
        if case_id is not None and not isinstance(case_id, str):
            raise ValueError(f"{path}:{line_number}: id metin olmalı")
        cases.append(
            EvaluationCase(
                query=query.strip(),
                relevant_parent_ids=frozenset(relevant),
                coin=coin,
                case_id=case_id,
            )
        )
    if not cases:
        raise ValueError(f"{path}: en az bir değerlendirme sorgusu gerekli")
    return cases


def _unique_document_ids(results: Sequence[Any]) -> list[str]:
    """Count a source document once even when multiple chunks are retrieved."""
    identifiers: list[str] = []
    seen: set[str] = set()
    for result in results:
        parent_id = getattr(result, "parent_id", None)
        identifier = str(parent_id or getattr(result, "key", ""))
        if identifier and identifier not in seen:
            seen.add(identifier)
            identifiers.append(identifier)
    return identifiers


def retrieval_metrics(
    retrieved_ids: Sequence[str], relevant_ids: set[str] | frozenset[str], k: int
) -> dict[str, float]:
    """Compute binary relevance metrics over unique source documents."""
    if k < 1:
        raise ValueError("k en az 1 olmalı")
    ranked = list(retrieved_ids[:k])
    relevant = set(relevant_ids)
    hits = [1 if identifier in relevant else 0 for identifier in ranked]
    relevant_retrieved = sum(hits)
    reciprocal_rank = next((1.0 / rank for rank, hit in enumerate(hits, 1) if hit), 0.0)
    dcg = sum(hit / math.log2(rank + 1) for rank, hit in enumerate(hits, 1))
    ideal_length = min(len(relevant), k)
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_length + 1))
    return {
        "precision": relevant_retrieved / k,
        "recall": relevant_retrieved / len(relevant) if relevant else 0.0,
        "hit_rate": float(relevant_retrieved > 0),
        "mrr": reciprocal_rank,
        "ndcg": dcg / ideal_dcg if ideal_dcg else 0.0,
    }


def evaluate_retrieval(
    search: Callable[[str, str | None, int], Sequence[Any]],
    cases: Sequence[EvaluationCase],
    *,
    ks: Sequence[int] = (1, 3, 5, 10),
) -> dict[str, Any]:
    """Run a retrieval function once per query and aggregate macro metrics."""
    cutoffs = sorted(set(int(k) for k in ks))
    if not cutoffs or cutoffs[0] < 1:
        raise ValueError("ks pozitif tamsayılardan oluşmalı")
    per_query: list[dict[str, Any]] = []
    accumulators = {k: {key: 0.0 for key in ("precision", "recall", "hit_rate", "mrr", "ndcg")} for k in cutoffs}
    for index, case in enumerate(cases, 1):
        # A source document can yield several ranked chunks; over-fetch before
        # deduplicating so the metrics describe source-document ranking.
        results = search(case.query, case.coin, cutoffs[-1] * 4)
        retrieved = _unique_document_ids(results)
        query_metrics = {}
        for k in cutoffs:
            metrics = retrieval_metrics(retrieved, case.relevant_parent_ids, k)
            query_metrics[str(k)] = metrics
            for name, value in metrics.items():
                accumulators[k][name] += value
        per_query.append(
            {
                "id": case.case_id or f"q{index}",
                "query": case.query,
                "coin": case.coin,
                "relevant_parent_ids": sorted(case.relevant_parent_ids),
                "retrieved_parent_ids": retrieved[: cutoffs[-1]],
                "metrics": query_metrics,
            }
        )
    aggregate = {
        str(k): {name: round(total / len(cases), 6) for name, total in values.items()}
        for k, values in accumulators.items()
    }
    return {"n_queries": len(cases), "cutoffs": cutoffs, "metrics": aggregate, "queries": per_query}
