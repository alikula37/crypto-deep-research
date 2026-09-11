"""Context Control Plane testleri."""

from crypto_deep_research.config import Settings
from crypto_deep_research.context.control_plane import ContextControlPlane
from crypto_deep_research.models import AnalysisResult, ContextObject, SourceRef
from crypto_deep_research.storage.db import Database


def _plane(tmp_path, budget=200) -> ContextControlPlane:
    settings = Settings(data_dir=tmp_path)
    db = Database(tmp_path / "test.db")
    return ContextControlPlane(db, settings, token_budget=budget)


def test_register_and_decide_keep(tmp_path):
    plane = _plane(tmp_path)
    result = AnalysisResult(
        key="technical",
        title="Teknik Analiz",
        summary="RSI notr",
        score=0.2,
        confidence=0.5,
        sources=[SourceRef(name="Binance")],
    )
    obj = plane.register_analysis("bitcoin", result)
    assert obj.priority >= 0.85
    assert plane.decide(obj) == "KEEP"


def test_pinned_returns_pin(tmp_path):
    plane = _plane(tmp_path)
    obj = ContextObject(key="k", content="x", pinned=True)
    assert plane.decide(obj) == "PIN"


def test_expired_ttl_drops(tmp_path):
    plane = _plane(tmp_path)
    obj = ContextObject(key="k", content="x", ttl_seconds=1)
    obj.updated_at = obj.updated_at.replace(year=2000)
    assert plane.decide(obj) == "DROP"


def test_compress_and_offload_cycle(tmp_path):
    plane = _plane(tmp_path)
    big_content = "veri " * 2000
    obj = ContextObject(
        key="big", content=big_content, tokens_estimate=5000, priority=0.5, data={"a": 1}
    )
    compressed = plane.compress(obj)
    assert len(compressed.content) < len(big_content)
    assert compressed.state == "compressed"

    offloaded = plane.offload(obj)
    assert offloaded.state == "offloaded"
    assert offloaded.blob_ref
    restored = plane.rehydrate("big")
    assert restored is not None
    assert restored.content == big_content
    assert restored.state == "hot"


def test_materialize_respects_budget(tmp_path):
    plane = _plane(tmp_path, budget=50)
    objects = [
        ContextObject(key=f"k{i}", content="x" * 400, tokens_estimate=100 + i * 100, priority=0.5)
        for i in range(4)
    ]
    text, stats = plane.materialize(objects)
    assert stats["tokens"] <= 50
    assert isinstance(text, str)
    assert sum(stats["groups"].values()) == len(objects)


def test_dedup_drops_duplicates(tmp_path):
    plane = _plane(tmp_path)
    a = ContextObject(key="a", content="ayni icerik", tokens_estimate=2, priority=0.9)
    b = ContextObject(key="b", content="ayni icerik", tokens_estimate=2, priority=0.9)
    groups = plane.apply_policy([a, b])
    assert len(groups["DROP"]) == 1
