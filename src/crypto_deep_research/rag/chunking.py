"""Token-offset document chunking for the local RAG index."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    text: str
    token_start: int
    token_count: int


def whitespace_offsets(text: str) -> list[tuple[int, int]]:
    """Fallback offsets used when the configured embedding model is unavailable."""
    return [match.span() for match in re.finditer(r"\S+", text)]


def split_text(
    text: str,
    offsets: list[tuple[int, int]],
    *,
    chunk_tokens: int,
    overlap_tokens: int,
) -> list[TextChunk]:
    """Split text at tokenizer offsets while preserving a configurable overlap."""
    if chunk_tokens < 1:
        raise ValueError("chunk_tokens must be positive")
    if overlap_tokens < 0 or overlap_tokens >= chunk_tokens:
        raise ValueError("overlap_tokens must be between zero and chunk_tokens - 1")

    valid_offsets = [(start, end) for start, end in offsets if 0 <= start < end <= len(text)]
    if not valid_offsets:
        return []

    chunks: list[TextChunk] = []
    start = 0
    while start < len(valid_offsets):
        end = min(start + chunk_tokens, len(valid_offsets))
        char_start = valid_offsets[start][0]
        char_end = valid_offsets[end - 1][1]
        chunks.append(
            TextChunk(
                text=text[char_start:char_end],
                token_start=start,
                token_count=end - start,
            )
        )
        if end == len(valid_offsets):
            break
        start = end - overlap_tokens

    return chunks
