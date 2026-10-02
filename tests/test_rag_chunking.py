"""Chunk boundaries respect token windows and retain their configured overlap."""

import pytest

from crypto_deep_research.rag.chunking import (
    reconstruct_chunk_text,
    split_text,
    whitespace_offsets,
)


def test_whitespace_token_chunks_keep_overlap_and_offsets():
    text = "one two three four five six seven eight nine"
    chunks = split_text(
        text,
        whitespace_offsets(text),
        chunk_tokens=4,
        overlap_tokens=1,
    )
    assert [(chunk.token_start, chunk.token_count) for chunk in chunks] == [
        (0, 4),
        (3, 4),
        (6, 3),
    ]
    assert chunks[0].text.endswith("four")
    assert chunks[1].text.startswith("four")
    assert chunks[-1].text.endswith("nine")


def test_split_text_filters_non_text_token_offsets():
    text = "alpha beta"
    chunks = split_text(
        text,
        [(0, 0), (0, 5), (6, 10), (10, 12)],
        chunk_tokens=2,
        overlap_tokens=0,
    )
    assert [chunk.text for chunk in chunks] == ["alpha beta"]
    assert chunks[0].token_count == 2


def test_split_text_rejects_overlap_at_or_above_chunk_size():
    with pytest.raises(ValueError, match="overlap_tokens"):
        split_text("one two", whitespace_offsets("one two"), chunk_tokens=2, overlap_tokens=2)


def test_reconstruct_chunk_text_removes_stored_overlap():
    chunks = [
        {"id": "doc#chunk-0", "chunk_index": 0, "token_start": 0, "token_count": 4,
         "text": "one two three four"},
        {"id": "doc#chunk-1", "chunk_index": 1, "token_start": 3, "token_count": 3,
         "text": "four five six"},
    ]

    assert reconstruct_chunk_text(chunks) == "one two three four five six"
