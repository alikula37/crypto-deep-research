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


def reconstruct_chunk_text(chunks: list[dict]) -> str:
    """Join stored chunks to recover source text from databases predating source archival."""
    if not chunks:
        return ""
    ordered = sorted(chunks, key=lambda item: (int(item.get("chunk_index") or 0), item["id"]))
    text = str(ordered[0].get("text") or "")
    previous_end = int(ordered[0].get("token_start") or 0) + int(
        ordered[0].get("token_count") or 0
    )
    for chunk in ordered[1:]:
        chunk_text = str(chunk.get("text") or "")
        token_start = int(chunk.get("token_start") or 0)
        token_overlap = max(0, previous_end - token_start)
        if token_overlap:
            overlap = _suffix_prefix_overlap(text, chunk_text)
            if overlap:
                text += chunk_text[overlap:]
            else:
                offsets = whitespace_offsets(chunk_text)
                trim_tokens = min(token_overlap, len(offsets))
                trim_at = offsets[trim_tokens - 1][1] if trim_tokens else 0
                text += chunk_text[trim_at:]
        else:
            text += "\n" + chunk_text
        previous_end = max(previous_end, token_start + int(chunk.get("token_count") or 0))
    return text


def _suffix_prefix_overlap(left: str, right: str) -> int:
    """Return the longest exact suffix of left that is also a prefix of right."""
    pattern = right[: min(len(left), len(right))]
    if not pattern:
        return 0

    prefix_lengths = [0] * len(pattern)
    matched = 0
    for index in range(1, len(pattern)):
        while matched and pattern[index] != pattern[matched]:
            matched = prefix_lengths[matched - 1]
        if pattern[index] == pattern[matched]:
            matched += 1
        prefix_lengths[index] = matched

    matched = 0
    for character in left[-len(pattern) :]:
        while matched and (matched == len(pattern) or character != pattern[matched]):
            matched = prefix_lengths[matched - 1]
        if matched < len(pattern) and character == pattern[matched]:
            matched += 1
    return matched
