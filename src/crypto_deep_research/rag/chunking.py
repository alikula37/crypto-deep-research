"""Token-budget document chunking for the local RAG index."""

from __future__ import annotations

import re
from bisect import bisect_left
from dataclasses import dataclass
from typing import Literal


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
    strategy: Literal["token", "sentence"] = "token",
) -> list[TextChunk]:
    """Split original source slices under a hard token budget.

    ``token`` retains fixed windows and an exact token overlap. ``sentence``
    packs complete sentences/paragraphs; overlap is a maximum token budget for
    complete trailing sentences, so its realized value can be zero. A sentence
    longer than the chunk budget falls back to non-overlapping token windows.
    """
    if chunk_tokens < 1:
        raise ValueError("chunk_tokens must be positive")
    if overlap_tokens < 0 or overlap_tokens >= chunk_tokens:
        raise ValueError("overlap_tokens must be between zero and chunk_tokens - 1")
    if strategy not in {"token", "sentence"}:
        raise ValueError("strategy must be 'token' or 'sentence'")

    valid_offsets = _valid_offsets(text, offsets)
    if not valid_offsets:
        return []
    if strategy == "sentence":
        return _split_sentences(text, valid_offsets, chunk_tokens, overlap_tokens)

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


# This is a conservative boundary heuristic, not a language model. Keeping
# common abbreviations intact is preferable to making tiny fragments from them.
_ABBREVIATIONS = frozenset(
    {
        "dr", "prof", "doç", "doc", "yrd", "sn", "say", "vb", "vd", "vs",
        "örn", "ör", "bkz", "yak", "no", "ltd", "mr", "mrs", "ms", "jr",
        "sr", "st", "etc", "approx", "dept", "fig", "inc", "vol", "pp",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept",
        "oct", "nov", "dec",
    }
)
_CLOSING_MARKS = frozenset("\"'”’»)]}")
_PUNCTUATION = re.compile(r"[.!?。！？]+")
_PARAGRAPH_BREAK = re.compile(r"\r?\n[ \t]*(?:\r?\n)+")
_DOTTED_INITIALS = re.compile(r"(?:[^\W\d_]\.)+[^\W\d_]$", re.UNICODE)


def _valid_offsets(text: str, offsets: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return [(start, end) for start, end in offsets if 0 <= start < end <= len(text)]


def _sentence_character_boundaries(text: str) -> list[int]:
    boundaries = {match.start() for match in _PARAGRAPH_BREAK.finditer(text)}
    for match in _PUNCTUATION.finditer(text):
        end = match.end()
        while end < len(text) and text[end] in _CLOSING_MARKS:
            end += 1
        # A URL/email/decimal's internal punctuation is followed immediately by
        # more text. Do not interpret those punctuation marks as sentence ends.
        if (
            end < len(text)
            and not text[end].isspace()
            and not any(mark in match.group() for mark in "。！？")
        ):
            continue
        if match.group() == ".":
            # Inspect only the preceding word/token. Repeatedly slicing the
            # complete prefix would make long, many-sentence reports quadratic.
            word_start = match.start()
            while word_start and text[word_start - 1].isalpha():
                word_start -= 1
            word = text[word_start : match.start()]
            token_start = match.start()
            while token_start and not text[token_start - 1].isspace():
                token_start -= 1
            dotted = text[token_start : match.start()]
            if (
                word.casefold() in _ABBREVIATIONS
                or (len(word) == 1 and word.isupper())
                or _DOTTED_INITIALS.fullmatch(dotted)
            ):
                continue
            # A numbered list marker starts a unit; it does not finish one.
            number_start = match.start()
            while number_start and text[number_start - 1].isdigit():
                number_start -= 1
            if number_start < match.start():
                marker_start = number_start
                while marker_start and text[marker_start - 1] in " \t\r":
                    marker_start -= 1
                if marker_start == 0 or text[marker_start - 1] == "\n":
                    continue
        boundaries.add(end)
    boundaries.add(len(text))
    return sorted(boundaries)


def sentence_token_spans(
    text: str, offsets: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Return contiguous half-open sentence/paragraph spans in valid-token indices.

    Segmentation uses punctuation followed by whitespace/end of text, common
    Turkish/English abbreviation protection, and blank-line paragraph breaks.
    Spans are returned before any oversized-sentence fallback. Token indices
    refer to the same filtered offsets as :func:`split_text`.
    """
    valid_offsets = _valid_offsets(text, offsets)
    if not valid_offsets:
        return []
    starts = [start for start, _ in valid_offsets]
    boundaries: set[int] = set()
    for boundary in _sentence_character_boundaries(text):
        end = bisect_left(starts, boundary)
        # A whitespace fallback (or a model token) can span punctuation plus
        # the next sentence's first word. Merge those units rather than moving
        # the boundary into that next sentence and claiming it is complete.
        if end and valid_offsets[end - 1][1] > boundary:
            continue
        boundaries.add(end)
    boundaries.add(len(valid_offsets))
    spans: list[tuple[int, int]] = []
    start = 0
    for end in sorted(boundaries):
        if end > start:
            spans.append((start, end))
            start = end
    return spans


def _split_sentences(
    text: str,
    offsets: list[tuple[int, int]],
    chunk_tokens: int,
    overlap_tokens: int,
) -> list[TextChunk]:
    # A unit is (token_start, token_end, is_complete_sentence). Oversized units
    # use token windows; their fragments cannot be reused as whole sentences.
    units: list[tuple[int, int, bool]] = []
    for start, end in sentence_token_spans(text, offsets):
        if end - start <= chunk_tokens:
            units.append((start, end, True))
        else:
            units.extend(
                (window_start, min(window_start + chunk_tokens, end), False)
                for window_start in range(start, end, chunk_tokens)
            )

    chunks: list[TextChunk] = []
    cursor = 0
    carry: list[int] = []
    while cursor < len(units):
        # Retaining a whole sentence is optional; adding new source content is
        # mandatory. Remove the oldest overlap until the next unit fits.
        while carry and units[cursor][1] - units[carry[0]][0] > chunk_tokens:
            carry.pop(0)
        first = carry[0] if carry else cursor
        start = units[first][0]
        while cursor < len(units) and units[cursor][1] - start <= chunk_tokens:
            cursor += 1
        end = units[cursor - 1][1]
        chunks.append(
            TextChunk(
                text=text[offsets[start][0] : offsets[end - 1][1]],
                token_start=start,
                token_count=end - start,
            )
        )
        if cursor == len(units):
            break
        carry = []
        for index in range(cursor - 1, first - 1, -1):
            unit_start, _, complete = units[index]
            if not complete or end - unit_start > overlap_tokens:
                break
            carry.append(index)
        carry.reverse()
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
