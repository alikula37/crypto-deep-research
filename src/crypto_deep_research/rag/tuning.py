"""Reproducible dev-only chunk sweeps over isolated SQLite/LanceDB indexes."""
from __future__ import annotations

import hashlib
import json
import random
import re
import sqlite3
import statistics
import tempfile
import time
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

from crypto_deep_research.config import Settings
from crypto_deep_research.models import RetrievedContext
from crypto_deep_research.rag.chunking import split_text
from crypto_deep_research.rag.embeddings import Embedder
from crypto_deep_research.rag.engine import RAGEngine
from crypto_deep_research.rag.evaluation import EvaluationCase, load_cases, retrieval_metrics
from crypto_deep_research.storage.db import Database


@dataclass(frozen=True)
class ChunkCandidate:
    chunk_tokens: int
    overlap_tokens: int
    strategy: str = "sentence"

    def __post_init__(self):
        if self.chunk_tokens < 1 or not 0 <= self.overlap_tokens < self.chunk_tokens:
            raise ValueError("0 <= overlap < chunk_tokens gerekli")
        if self.strategy not in {"sentence", "token"}:
            raise ValueError("strategy sentence veya token olmalı")

    @property
    def key(self) -> str:
        return f"{self.strategy}-{self.chunk_tokens}-{self.overlap_tokens}"


DEFAULT_CANDIDATES = tuple(ChunkCandidate(size, overlap) for size, overlap in (
    (96, 16), (160, 27), (240, 40), (320, 53), (448, 75), (240, 0), (240, 80),
))


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def snapshot_sources(db_path: Path) -> list[dict]:
    """A single read transaction; no migrations/writes against the running product."""
    with sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(
            "SELECT * FROM rag_source_documents ORDER BY id"
        )]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def evidence_alternatives(item: dict) -> list[dict]:
    """One required fact may have several valid source/text alternatives."""
    return item.get("alternatives", [item])


def load_tuning_cases(path: Path) -> tuple[list[EvaluationCase], dict[str, dict]]:
    cases = load_cases(path, split="dev")
    metadata = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("split") != "dev":
            continue
        case_id = row.get("id")
        if not isinstance(case_id, str) or not case_id.strip() or case_id.strip() in metadata:
            raise ValueError("Dev sorgularında benzersiz, boş olmayan id gerekli")
        for name in ("group", "label_status", "category"):
            if name in row and (not isinstance(row[name], str) or not row[name].strip()):
                raise ValueError(f"{case_id}: {name} boş olmayan bir metin olmalı")
        evidence = row.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"{case_id}: en az bir evidence pasajı gerekli")
        for item in evidence:
            if not isinstance(item, dict):
                raise ValueError(f"{case_id}: evidence nesne olmalı")
            alternatives = evidence_alternatives(item)
            if not isinstance(alternatives, list) or not alternatives:
                raise ValueError(f"{case_id}: alternatives boş olmayan liste olmalı")
            for variant in alternatives:
                if not isinstance(variant, dict) or variant.get("parent_id") not in row["relevant_parent_ids"]:
                    raise ValueError(f"{case_id}: evidence parent_id ilgili kaynaklar içinde olmalı")
                if not isinstance(variant.get("text"), str) or not normalize(variant["text"]):
                    raise ValueError(f"{case_id}: evidence text boş olamaz")
        metadata[case_id.strip()] = {
            "evidence": evidence,
            "label_status": row.get("label_status", "unreviewed"),
            "group": row.get("group") or case_id.strip(),
            "category": row.get("category", "unspecified"),
        }
    return cases, metadata


def validate_sources(sources: list[dict], cases: list[EvaluationCase], metadata: dict) -> None:
    by_id = {row["id"]: row for row in sources}
    if not sources or len(by_id) != len(sources):
        raise ValueError("Korpus boş veya kaynak kimlikleri yineleniyor")
    for case in cases:
        for parent in case.relevant_parent_ids:
            row = by_id.get(parent)
            if row is None or (case.coin and row["coin"] != case.coin):
                raise ValueError(f"{case.case_id}: kaynak yok veya coin filtresine uymuyor: {parent}")
        for item in metadata[case.case_id]["evidence"]:
            for variant in evidence_alternatives(item):
                if normalize(variant["text"]) not in normalize(by_id[variant["parent_id"]]["text"]):
                    raise ValueError(f"{case.case_id}: evidence metni kaynak sürümünde bulunamadı")


def context_metrics(results: list, evidence: list[dict], k: int) -> dict:
    """Exact evidence spans must survive inside one of the actual top-k chunks."""
    selected = results[:k]
    hits = [any(
        (item.parent_id or item.key) == variant["parent_id"]
        and normalize(variant["text"]) in normalize(item.content)
        for variant in evidence_alternatives(label) for item in selected
    ) for label in evidence]
    return {"evidence_coverage": sum(hits) / len(hits), "evidence_complete": float(all(hits))}


def paired_interval(candidate: dict, baseline: dict, *, seed: int = 37) -> dict:
    """Cluster bootstrap of paired dev evidence differences, descriptive only."""
    base = {row["id"]: row for row in baseline["queries"]}
    groups = defaultdict(list)
    for row in candidate["queries"]:
        groups[row["group"]].append(row["evidence_coverage"] - base[row["id"]]["evidence_coverage"])
    clusters = list(groups.values())
    rng = random.Random(seed)
    means = []
    for _ in range(2000):
        values = [value for group in rng.choices(clusters, k=len(clusters)) for value in group]
        means.append(statistics.mean(values))
    means.sort()
    return {"mean_delta": round(statistics.mean([
        value for group in clusters for value in group
    ]), 6), "ci95": [round(means[49], 6), round(means[1949], 6)],
        "clusters": len(clusters), "resamples": 2000, "seed": seed}


def select_candidate(runs: list[dict], baseline_key: str, tolerance: float = 0.02) -> dict:
    """Freeze the rule before running: evidence, source recall/nDCG, then token cost."""
    if not 0 <= tolerance < 1:
        raise ValueError("quality tolerance 0 <= değer < 1 olmalı")
    baseline = next(run for run in runs if run["key"] == baseline_key)
    pool = runs
    for metric in ("evidence_coverage", "recall", "ndcg"):
        best = max(run["metrics"][metric] for run in pool)
        pool = [run for run in pool if run["metrics"][metric] >= best - tolerance]
    selected = min(pool, key=lambda run: (
        run["cost"]["mean_context_tokens"], run["index"]["chunks"], run["key"]
    ))
    return {"candidate": selected["key"], "settings": selected["settings"],
            "baseline": baseline_key, "quality_tolerance": tolerance,
            "eligible_candidates": [run["key"] for run in pool],
            "paired_evidence_vs_baseline": paired_interval(selected, baseline),
            "rule": "evidence coverage → source recall → nDCG (within tolerance); then context tokens, chunks",
            "status": "dev-recommendation-not-final", "production_changed": False}


class StrictEmbedder:
    """Reuse one model but abort a sweep instead of silently falling back to BM25."""
    def __init__(self, delegate: Embedder):
        self.delegate = delegate

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def embed(self, texts):
        vectors = self.delegate.embed(texts)
        if vectors is None or len(vectors) != len(texts):
            raise RuntimeError("Embedding başarısız; benchmark durduruldu")
        return vectors

    def embed_one(self, text):
        return self.embed([text])[0]


def rescore_sweep(report: dict, sources: list[dict], dataset: Path) -> dict:
    """Rejudge frozen top-k rankings after label review, without rerunning retrieval."""
    if digest(sources) != report["corpus"]["sha256"]:
        raise ValueError("Yeniden puanlama için aynı kaynak snapshot'ı gerekli")
    cases, metadata = load_tuning_cases(dataset)
    validate_sources(sources, cases, metadata)
    frozen_cases = {row["id"]: row for row in report["dataset"]["cases"]}
    if {case.case_id for case in cases} != set(frozen_cases) or any(
        (case.query, case.coin) != (frozen_cases[case.case_id]["query"], frozen_cases[case.case_id]["coin"])
        for case in cases
    ):
        raise ValueError("Soru/coin/kimlik değişmiş: yeni sorgular için yeniden sweep gerekli")
    embedder = Embedder(report["embedding"]["model"])
    offsets = {row["id"]: embedder.token_offsets(row["text"]) for row in sources}
    if any(value is None for value in offsets.values()) or embedder.model_name != report["embedding"]["model"]:
        raise RuntimeError("Aynı tokenizer kullanılamadı")
    result = deepcopy(report)
    by_case = {case.case_id: case for case in cases}
    verified_layouts = True
    for run in result["runs"]:
        by_chunk = {}
        layout = []
        for row in sources:
            chunks = split_text(row["text"], offsets[row["id"]], **run["settings"])
            layout.extend(asdict(chunk) for chunk in chunks)
            for index, chunk in enumerate(chunks):
                key = row["id"] if len(chunks) == 1 else f"{row['id']}#chunk-{index:06d}"
                by_chunk[key] = RetrievedContext(key=key, parent_id=row["id"], content=chunk.text, score=0)
        recorded_layout = run["index"].get("chunk_layout_sha256")
        if recorded_layout and recorded_layout != digest(layout):
            raise ValueError("Chunk sınırları/metinleri değişmiş: eski sıralama yeniden puanlanamaz")
        if len(layout) != run["index"]["chunks"]:
            raise ValueError("Chunk sayısı değişmiş: eski sıralama yeniden puanlanamaz")
        verified_layouts &= bool(recorded_layout)
        for query in run["queries"]:
            case = by_case[query["id"]]
            try:
                contexts = [by_chunk[key] for key in query["retrieved_chunk_ids"]]
            except KeyError as exc:
                raise ValueError("Chunk sınırları değişmiş: eski sıralama yeniden puanlanamaz") from exc
            query.update(retrieval_metrics(query["retrieved_parent_ids"], case.relevant_parent_ids, report["k"]))
            query.update(context_metrics(contexts, metadata[case.case_id]["evidence"], report["k"]))
            query["group"] = metadata[case.case_id]["group"]
        run["metrics"] = {name: round(statistics.mean(row[name] for row in run["queries"]), 6)
                          for name in run["metrics"]}
    dev_rows = [{"id": case.case_id, "query": case.query, "coin": case.coin,
                 "relevant_parent_ids": sorted(case.relevant_parent_ids), **metadata[case.case_id]}
                for case in cases]
    result["dataset"] = {"dev_sha256": digest(dev_rows), "label_statuses": sorted({
        row["label_status"] for row in metadata.values()}), "cases": dev_rows}
    result["selection"] = select_candidate(result["runs"], report["selection"]["baseline"],
                                            report["selection"]["quality_tolerance"])
    result["rescore"] = {"original_report_sha256": digest(report),
                         "created_at": datetime.now(timezone.utc).isoformat(),
                         "retrieval_repeated": False, "timings_reused": True,
                         "all_chunk_layouts_verified": verified_layouts,
                         "implementation_sha256": digest({
                             name: (Path(__file__).parent / name).read_text(encoding="utf-8")
                             for name in ("tuning.py", "chunking.py", "embeddings.py", "evaluation.py")}),
                         "versions": {package: version(package)
                                      for package in ("fastembed", "lancedb", "tokenizers")}}
    return result


def run_sweep(
    sources: list[dict], dataset: Path, settings: Settings, *,
    candidates: tuple[ChunkCandidate, ...] = DEFAULT_CANDIDATES,
    k: int = 5, retrieval: str = "hybrid", tolerance: float = 0.02,
    embedding_batch_size: int = 32,
    progress=None,
) -> dict:
    if k < 1 or retrieval not in {"dense", "bm25", "hybrid"}:
        raise ValueError("k pozitif, retrieval dense/bm25/hybrid olmalı")
    if not 0 <= tolerance < 1:
        raise ValueError("quality tolerance 0 <= değer < 1 olmalı")
    if not candidates or len({candidate.key for candidate in candidates}) != len(candidates):
        raise ValueError("En az bir aday gerekli; adaylar benzersiz olmalı")
    baseline = ChunkCandidate(settings.rag_chunk_tokens, settings.rag_chunk_overlap_tokens,
                              settings.rag_chunk_strategy)
    if baseline not in candidates:
        candidates = (*candidates, baseline)
    cases, metadata = load_tuning_cases(dataset)
    validate_sources(sources, cases, metadata)
    embedder = StrictEmbedder(Embedder(settings.embedding_model, settings.embeddings_enabled,
                                     batch_size=embedding_batch_size))
    # Warm load, resolve actual model/tokenizer, reject any model substitution.
    offsets = {row["id"]: embedder.token_offsets(row["text"]) for row in sources}
    if any(value is None for value in offsets.values()) or embedder.model_name != settings.embedding_model:
        raise RuntimeError("İstenen embedding/tokenizer yüklenemedi; fallback ile deney yapılmaz")
    limit = embedder.max_input_tokens
    if limit is None:
        raise RuntimeError("Embedding giriş sınırı bilinmiyor; kırpmasız deney doğrulanamaz")
    for case in cases:
        if embedder.input_token_count(case.query) > limit:
            raise ValueError(f"{case.case_id}: soru embedding sınırını aşıyor")
    runs = []
    for candidate in candidates:
        if progress:
            progress(f"{candidate.key}: izole indeks kuruluyor")
        chunks = [chunk for row in sources for chunk in split_text(
            row["text"], offsets[row["id"]], **asdict(candidate)
        )]
        counts = [embedder.input_token_count(chunk.text) for chunk in chunks]
        if any(count is None or count > limit for count in counts):
            raise ValueError(f"{candidate.key}: bağımsız chunk token sayısı model sınırını aşıyor")
        with tempfile.TemporaryDirectory(prefix="cdr-chunk-sweep-") as directory:
            state = Path(directory)
            scratch_settings = settings.model_copy(update={
                "state_dir": state, "rag_chunk_tokens": candidate.chunk_tokens,
                "rag_chunk_overlap_tokens": candidate.overlap_tokens,
                "rag_chunk_strategy": candidate.strategy, "rag_reranker_model": None,
            })
            db = Database(scratch_settings.db_path)
            try:
                engine = RAGEngine(db, scratch_settings, embedder=embedder)
                engine.store.strict = True
                started = time.perf_counter()
                indexed = engine._ingest_rows(sources)
                build_seconds = time.perf_counter() - started
                if not engine.store.available or engine.store.count() != indexed or indexed != len(chunks):
                    raise RuntimeError("Vektör/chunk sayısı eşleşmedi; eksik indeksle ölçüm yapılmaz")
                queries = []
                # Fixed warm-up query, excluded from measured query latency.
                engine.search(cases[0].query, coin=cases[0].coin, k=k, mode=retrieval)
                for case in cases:
                    started = time.perf_counter()
                    results = engine.search(case.query, coin=case.coin, k=k, mode=retrieval)
                    latency_ms = (time.perf_counter() - started) * 1000
                    parent_ids = list(dict.fromkeys(item.parent_id or item.key for item in results))
                    metrics = retrieval_metrics(parent_ids, case.relevant_parent_ids, k)
                    evidence = context_metrics(results, metadata[case.case_id]["evidence"], k)
                    context_tokens = sum(embedder.input_token_count(item.content) for item in results)
                    queries.append({"id": case.case_id, "group": metadata[case.case_id]["group"],
                                    **metrics, **evidence, "context_tokens": context_tokens,
                                    "latency_ms": round(latency_ms, 3),
                                    "retrieved_chunk_ids": [item.key for item in results],
                                    "retrieved_parent_ids": parent_ids})
                if not engine.store.available:
                    raise RuntimeError("LanceDB deney sırasında kullanılamadı")
                runs.append({"key": candidate.key, "settings": asdict(candidate),
                             "index": {"chunks": indexed, "vectors": engine.store.count(),
                                       "chunk_layout_sha256": digest([asdict(chunk) for chunk in chunks]),
                                       "max_input_tokens": max(counts),
                                       "indexed_source_tokens": sum(chunk.token_count for chunk in chunks),
                                       "build_seconds": round(build_seconds, 3)},
                             "metrics": {name: round(statistics.mean(row[name] for row in queries), 6)
                                         for name in ("precision", "recall", "hit_rate", "mrr", "ndcg",
                                                      "evidence_coverage", "evidence_complete")},
                             "cost": {"mean_context_tokens": round(statistics.mean(
                                 row["context_tokens"] for row in queries), 3),
                                      "median_latency_ms": round(statistics.median(
                                          row["latency_ms"] for row in queries), 3)},
                             "queries": queries})
                if progress:
                    progress(f"{candidate.key}: coverage={runs[-1]['metrics']['evidence_coverage']:.3f}, "
                             f"{indexed} chunk")
            finally:
                db.close()
    dev_rows = [{"id": case.case_id, "query": case.query, "coin": case.coin,
                 "relevant_parent_ids": sorted(case.relevant_parent_ids), **metadata[case.case_id]}
                for case in cases]
    return {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
            "implementation_sha256": digest({
                name: (Path(__file__).parent / name).read_text(encoding="utf-8")
                for name in ("tuning.py", "chunking.py", "engine.py", "embeddings.py", "store.py")}),
            "versions": {package: version(package) for package in ("fastembed", "lancedb", "tokenizers")},
            "split": "dev", "test_evaluated": False, "n_queries": len(cases), "k": k,
            "corpus": {"sources": len(sources), "sha256": digest(sources)},
            "dataset": {"dev_sha256": digest(dev_rows), "label_statuses": sorted({
                row["label_status"] for row in metadata.values()}), "cases": dev_rows},
            "embedding": {"model": embedder.model_name, "input_limit": limit,
                          "batch_size": embedding_batch_size},
            "retrieval": {"mode": retrieval, "reranker": None,
                          "source_metric_scope": "unique parents in actual top-k chunks; no overfetch",
                          "context_tokens": "E5 standalone counts with special tokens; LLM cost proxy, not billing",
                          "latency": "warm sequential search including query embedding; one pass per query"},
            "runs": runs, "selection": select_candidate(runs, baseline.key, tolerance)}
