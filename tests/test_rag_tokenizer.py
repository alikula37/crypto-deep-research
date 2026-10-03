"""Full-document RAG offsets must not inherit inference truncation/padding."""

from types import SimpleNamespace

from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace
from tokenizers.processors import TemplateProcessing

from crypto_deep_research.rag.chunking import split_text
from crypto_deep_research.rag.embeddings import Embedder


def test_full_document_offsets_preserve_embedding_tokenizer_limits():
    tokenizer = Tokenizer(
        WordLevel({"[UNK]": 0, "[PAD]": 1, "risk": 2, "son": 3}, unk_token="[UNK]")
    )
    tokenizer.pre_tokenizer = Whitespace()
    tokenizer.enable_truncation(max_length=512)
    tokenizer.enable_padding(length=512, pad_id=1, pad_token="[PAD]")
    embedder = Embedder("unit-test-cached-model")
    embedder._model = SimpleNamespace(model=SimpleNamespace(tokenizer=tokenizer))
    text = " ".join(["risk"] * 899 + ["son"])

    offsets = embedder.token_offsets(text)

    assert offsets is not None and len(offsets) == 900
    assert offsets[0] == (0, 4)
    assert offsets[-1][1] == len(text)
    assert all(0 <= start < end <= len(text) for start, end in offsets)
    assert [text[start:end] for start, end in offsets] == ["risk"] * 899 + ["son"]
    chunks = split_text(text, offsets, chunk_tokens=240, overlap_tokens=40)
    assert [chunk.token_start for chunk in chunks] == [0, 200, 400, 600, 800]
    assert chunks[-1].text.endswith("son")

    # The next short document must also get only real offsets. Inference still
    # truncates long text at 512 and pads short text to the configured 512.
    assert embedder.token_offsets("son") == [(0, 3)]
    assert tokenizer.truncation["max_length"] == 512
    assert tokenizer.padding["length"] == 512
    assert len(tokenizer.encode(text).tokens) == 512
    assert len(tokenizer.encode("son").tokens) == 512


def test_standalone_input_count_includes_special_tokens_without_truncation():
    tokenizer = Tokenizer(WordLevel({"[UNK]": 0, "[CLS]": 1, "[SEP]": 2, "risk": 3}, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = Whitespace()
    tokenizer.post_processor = TemplateProcessing(single="[CLS] $A [SEP]", special_tokens=[("[CLS]", 1), ("[SEP]", 2)])
    tokenizer.enable_truncation(max_length=512)
    embedder = Embedder("unit-test-cached-model")
    embedder._model = SimpleNamespace(model=SimpleNamespace(tokenizer=tokenizer))
    text = " ".join(["risk"] * 511)
    assert len(embedder.token_offsets(text)) == 511
    assert embedder.input_token_count(text) == 513
    assert embedder.max_input_tokens == 512
    assert len(tokenizer.encode(text).ids) == 512


def test_embedding_batch_limit_is_forwarded_without_changing_model_input():
    calls = []
    def embed(texts, **kwargs):
        calls.append((texts, kwargs))
        return [[1.0, 0.0] for _ in texts]
    wrapper = Embedder('test', batch_size=32)
    wrapper._model = SimpleNamespace(embed=embed)
    assert wrapper.embed(['original passage']) == [[1.0, 0.0]]
    assert calls == [(['original passage'], {'batch_size': 32})]
