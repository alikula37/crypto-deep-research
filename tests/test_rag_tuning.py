"""Selection uses dev evidence in actual chunks; isolated sweeps cannot touch product indexes."""
import json
from types import SimpleNamespace

import pytest

from crypto_deep_research.config import Settings
from crypto_deep_research.rag.chunking import whitespace_offsets
from crypto_deep_research.rag.tuning import (
    ChunkCandidate,
    context_metrics,
    load_tuning_cases,
    paired_interval,
    run_sweep,
    select_candidate,
    snapshot_sources,
    validate_sources,
)
from crypto_deep_research.storage.db import Database


def test_evidence_requires_right_parent_and_one_complete_chunk():
    label = [{"parent_id": "a", "text": "risk depends on leverage"}]
    results = [SimpleNamespace(parent_id="b", key="b", content=label[0]["text"]),
               SimpleNamespace(parent_id="a", key="a1", content="risk depends"),
               SimpleNamespace(parent_id="a", key="a2", content="on leverage")]
    assert context_metrics(results, label, 3)["evidence_coverage"] == 0
    results.append(SimpleNamespace(parent_id="a", key="a3", content="risk\n depends on leverage"))
    assert context_metrics(results, label, 3)["evidence_coverage"] == 0
    assert context_metrics(results, label, 4)["evidence_complete"] == 1


def write_dataset(path):
    rows = [{"id": "dev-1", "split": "dev", "query": "risk", "coin": "bitcoin",
             "relevant_parent_ids": ["a"], "evidence": [{"parent_id": "a", "text": "risk rises"}],
             "label_status": "agent-drafted-needs-human-review"},
            {"id": "test-1", "split": "test", "query": "held out", "relevant_parent_ids": ["missing"]}]
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))


def test_tuning_never_uses_test_labels_and_rejects_missing_evidence(tmp_path):
    path = tmp_path / 'labels.jsonl'
    write_dataset(path)
    cases, metadata = load_tuning_cases(path)
    assert [case.case_id for case in cases] == ['dev-1']
    sources = [{"id": "a", "text": "risk rises", "coin": "bitcoin"}]
    validate_sources(sources, cases, metadata)
    sources[0]['text'] = 'different revision'
    with pytest.raises(ValueError, match='kaynak sürümünde'):
        validate_sources(sources, cases, metadata)
    path.write_text(path.read_text().splitlines()[0] + '\n' + path.read_text().splitlines()[0])
    with pytest.raises(ValueError, match='benzersiz'):
        load_tuning_cases(path)


def run_record(key, quality, tokens):
    return {"key": key, "settings": {}, "metrics": {
        "evidence_coverage": quality, "recall": 1, "ndcg": 1},
        "cost": {"mean_context_tokens": tokens}, "index": {"chunks": 10},
        "queries": [{"id": "q1", "group": "g1", "evidence_coverage": quality}]}


def test_selection_rejects_cheap_but_worse_evidence_and_reports_uncertainty():
    baseline = run_record('baseline', .9, 240)
    cheap_bad = run_record('cheap-bad', .5, 60)
    equivalent = run_record('equivalent', .89, 160)
    choice = select_candidate([baseline, cheap_bad, equivalent], 'baseline')
    assert choice['candidate'] == 'equivalent'
    assert choice['production_changed'] is False
    assert choice['paired_evidence_vs_baseline']['ci95'] == [-.01, -.01]
    assert paired_interval(baseline, baseline)['ci95'] == [0, 0]


class FakeEmbedder:
    model_name = 'fake'
    max_input_tokens = 32

    def __init__(self, *_args):
        pass

    def token_offsets(self, text):
        return whitespace_offsets(text)

    def input_token_count(self, text):
        return len(text.split()) + 2

    def embed(self, texts):
        return [[1.0, float('risk' in text), float(len(text.split())), 0.0] for text in texts]


def test_sweep_uses_real_scratch_stores_preserves_original_and_counts_actual_top_k(tmp_path, monkeypatch):
    monkeypatch.setattr('crypto_deep_research.rag.tuning.Embedder', FakeEmbedder)
    dataset = tmp_path / 'dev.jsonl'
    write_dataset(dataset)
    settings = Settings(_env_file=None, state_dir=tmp_path / 'product', embedding_model='fake',
                        rag_chunk_tokens=6, rag_chunk_overlap_tokens=0)
    db = Database(settings.db_path)
    db.save_rag_source_document('a', 'bitcoin', 'report', 'test', '', 'risk rises. price falls. risk falls.')
    before = snapshot_sources(settings.db_path)
    db.close()
    report = run_sweep(before, dataset, settings, candidates=(ChunkCandidate(3, 0),), k=1)
    assert snapshot_sources(settings.db_path) == before
    assert not settings.vector_dir.exists()
    assert report['n_queries'] == 1 and report['test_evaluated'] is False
    assert len(report['runs']) == 2  # baseline automatically included
    assert all(run['index']['vectors'] == run['index']['chunks'] for run in report['runs'])
    assert all(len(run['queries'][0]['retrieved_chunk_ids']) == 1 for run in report['runs'])


def test_sweep_aborts_on_retokenized_overflow_before_embedding(tmp_path, monkeypatch):
    class Overflow(FakeEmbedder):
        def input_token_count(self, text):
            return 100 if len(text.split()) > 1 else 3
    monkeypatch.setattr('crypto_deep_research.rag.tuning.Embedder', Overflow)
    dataset = tmp_path / 'dev.jsonl'
    write_dataset(dataset)
    settings = Settings(_env_file=None, embedding_model='fake')
    sources = [{"id": "a", "coin": "bitcoin", "text": "risk rises"}]
    with pytest.raises(ValueError, match='model sınırını'):
        run_sweep(sources, dataset, settings)


def test_benchmark_store_search_failure_cannot_become_bm25_success(tmp_path, monkeypatch):
    from crypto_deep_research.rag.store import VectorStore

    store = VectorStore(tmp_path / 'vectors', strict=True)
    class BrokenTable:
        def search(self, *_args):
            raise OSError('broken index')
    monkeypatch.setattr(store, '_table', lambda: BrokenTable())
    with pytest.raises(RuntimeError, match='arama başarısız'):
        store.search([1.0, 0.0])


def test_malformed_bootstrap_group_rejected_before_expensive_indexing(tmp_path):
    dataset = tmp_path / 'dev.jsonl'
    write_dataset(dataset)
    row = json.loads(dataset.read_text().splitlines()[0])
    row['group'] = ['unhashable']
    dataset.write_text(json.dumps(row))
    with pytest.raises(ValueError, match='group boş olmayan'):
        load_tuning_cases(dataset)


def test_alternative_support_is_not_counted_as_an_extra_required_fact(tmp_path):
    labels = [{'alternatives': [{'parent_id': 'a', 'text': 'risk rises'},
                                {'parent_id': 'b', 'text': 'higher risk'}]}]
    result = [SimpleNamespace(parent_id='b', key='b1', content='higher risk here')]
    assert context_metrics(result, labels, 1) == {'evidence_coverage': 1, 'evidence_complete': 1}
    dataset = tmp_path / 'dev.jsonl'
    row = {'id': 'q1', 'split': 'dev', 'query': 'risk?', 'relevant_parent_ids': ['a', 'b'],
           'evidence': labels}
    dataset.write_text(json.dumps(row))
    cases, metadata = load_tuning_cases(dataset)
    validate_sources([{'id': 'a', 'coin': None, 'text': 'risk rises'},
                      {'id': 'b', 'coin': None, 'text': 'higher risk'}], cases, metadata)


def test_rescore_requires_frozen_query_source_and_chunk_boundaries(tmp_path, monkeypatch):
    from crypto_deep_research.rag.tuning import rescore_sweep
    monkeypatch.setattr('crypto_deep_research.rag.tuning.Embedder', FakeEmbedder)
    dataset = tmp_path / 'dev.jsonl'
    write_dataset(dataset)
    settings = Settings(_env_file=None, embedding_model='fake', rag_chunk_tokens=6, rag_chunk_overlap_tokens=0)
    sources = [{'id': 'a', 'coin': 'bitcoin', 'text': 'risk rises. price falls.',
                'kind': 'report', 'source': 'test', 'url': '', 'ts': 1}]
    report = run_sweep(sources, dataset, settings, candidates=(ChunkCandidate(6, 0),), k=1)
    revised = rescore_sweep(report, sources, dataset)
    assert revised['runs'] == report['runs']
    assert revised['rescore']['all_chunk_layouts_verified'] is True
    row = json.loads(dataset.read_text().splitlines()[0])
    row['query'] = 'different question'
    dataset.write_text(json.dumps(row))
    with pytest.raises(ValueError, match='Soru/coin/kimlik'):
        rescore_sweep(report, sources, dataset)
    write_dataset(dataset)
    report['runs'][0]['index']['chunk_layout_sha256'] = 'different boundaries'
    with pytest.raises(ValueError, match='sınırları/metinleri'):
        rescore_sweep(report, sources, dataset)
