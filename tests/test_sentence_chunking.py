"""Sentence-aware chunks retain evidence boundaries under a hard token budget."""

import pytest

from crypto_deep_research.rag.chunking import (
    sentence_token_spans,
    split_text,
    whitespace_offsets,
)


def sentence_texts(text, offsets=None):
    offsets = offsets if offsets is not None else whitespace_offsets(text)
    return [
        text[offsets[start][0] : offsets[end - 1][1]]
        for start, end in sentence_token_spans(text, offsets)
    ]


def assert_coverage(text, chunks, budget, overlap):
    offsets = whitespace_offsets(text)
    assert chunks[0].token_start == 0
    previous_end = 0
    previous_start = -1
    for chunk in chunks:
        assert 0 < chunk.token_count <= budget
        assert previous_start < chunk.token_start <= previous_end
        assert previous_end - chunk.token_start <= overlap
        end = chunk.token_start + chunk.token_count
        assert end > previous_end
        assert chunk.text == text[offsets[chunk.token_start][0] : offsets[end - 1][1]]
        previous_start = chunk.token_start
        previous_end = end
    assert previous_end == len(offsets)


def test_complete_sentence_overlap_does_not_cut_evidence_or_emit_duplicate_tail():
    text = "Alpha one two. Beta three four. Gamma five six. Delta seven eight."
    chunks = split_text(
        text, whitespace_offsets(text), chunk_tokens=6, overlap_tokens=3,
        strategy="sentence",
    )
    assert [chunk.text for chunk in chunks] == [
        "Alpha one two. Beta three four.",
        "Beta three four. Gamma five six.",
        "Gamma five six. Delta seven eight.",
    ]
    assert_coverage(text, chunks, 6, 3)


def test_overlap_budget_smaller_than_sentence_produces_zero_actual_overlap():
    text = "Alpha one two. Beta three four. Gamma five six. Delta seven eight."
    chunks = split_text(
        text, whitespace_offsets(text), chunk_tokens=6, overlap_tokens=2,
        strategy="sentence",
    )
    assert [(chunk.token_start, chunk.token_count) for chunk in chunks] == [(0, 6), (6, 6)]
    assert_coverage(text, chunks, 6, 2)


def test_large_overlap_drops_oldest_whole_sentence_to_make_room_for_new_evidence():
    text = "Alpha. Beta two. Gamma three four five. Delta six."
    chunks = split_text(
        text, whitespace_offsets(text), chunk_tokens=6, overlap_tokens=5,
        strategy="sentence",
    )
    assert [(chunk.token_start, chunk.token_count) for chunk in chunks] == [
        (0, 3), (1, 6), (3, 6),
    ]
    assert [chunk.text for chunk in chunks] == [
        "Alpha. Beta two.",
        "Beta two. Gamma three four five.",
        "Gamma three four five. Delta six.",
    ]
    assert_coverage(text, chunks, 6, 5)


def test_overlap_cannot_prevent_advancing_even_when_near_chunk_budget():
    text = "Alpha one two. Beta three four. Gamma five six."
    chunks = split_text(
        text, whitespace_offsets(text), chunk_tokens=5, overlap_tokens=4,
        strategy="sentence",
    )
    assert [chunk.token_start for chunk in chunks] == [0, 3, 6]
    assert all(chunk.token_count == 3 for chunk in chunks)
    assert_coverage(text, chunks, 5, 4)


def test_single_oversized_sentence_uses_hard_windows_without_partial_sentence_overlap():
    text = "one two three four five six seven. Fine ends. Next ends."
    chunks = split_text(
        text, whitespace_offsets(text), chunk_tokens=4, overlap_tokens=3,
        strategy="sentence",
    )
    assert sentence_token_spans(text, whitespace_offsets(text)) == [(0, 7), (7, 9), (9, 11)]
    assert [chunk.text for chunk in chunks] == [
        "one two three four", "five six seven.", "Fine ends. Next ends.",
    ]
    assert_coverage(text, chunks, 4, 3)


def test_complete_sentence_after_long_sentence_fragment_can_be_reused():
    text = "one two three four five. Fine ends. Next ends. Last ends."
    chunks = split_text(
        text, whitespace_offsets(text), chunk_tokens=4, overlap_tokens=2,
        strategy="sentence",
    )
    assert [chunk.text for chunk in chunks] == [
        "one two three four", "five. Fine ends.", "Fine ends. Next ends.",
        "Next ends. Last ends.",
    ]
    assert_coverage(text, chunks, 4, 2)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Dr. Ayşe, Prof. Jones ile %3.5 ve 1.000 değerlerini inceledi. Sonuç geçici.",
            ["Dr. Ayşe, Prof. Jones ile %3.5 ve 1.000 değerlerini inceledi.", "Sonuç geçici."],
        ),
        (
            "Fonlama vb. tek başına yeterli değil. Risk vs. ek koşullar gerektirir!",
            ["Fonlama vb. tek başına yeterli değil.", "Risk vs. ek koşullar gerektirir!"],
        ),
        (
            "Mr. Smith and A. Jones inspected the U.S. report. It passed.",
            ["Mr. Smith and A. Jones inspected the U.S. report.", "It passed."],
        ),
        (
            "Use e.g. funding and i.e. leverage together. Then compare.",
            ["Use e.g. funding and i.e. leverage together.", "Then compare."],
        ),
        (
            "Kaynak https://example.com/a.b?q=1.2 ve mail a.b@example.com. Yeni cümle.",
            ["Kaynak https://example.com/a.b?q=1.2 ve mail a.b@example.com.", "Yeni cümle."],
        ),
        (
            '"Risk kesin değil." (Devam?) Hayır! Sonuç...',
            ['"Risk kesin değil."', "(Devam?)", "Hayır!", "Sonuç..."],
        ),
        ("Başlık\n\nİlk paragraf\r\n \r\nİkinci paragraf", ["Başlık", "İlk paragraf", "İkinci paragraf"]),
        ("1. İlk madde\n\n2. İkinci madde.", ["1. İlk madde", "2. İkinci madde."]),
        ("Neden?! Evet!!! Son.", ["Neden?!", "Evet!!!", "Son."]),
        ("Risk yükseldi。Sonuç değişti。", ["Risk yükseldi。Sonuç değişti。"]),
        ("punctuation free text", ["punctuation free text"]),
    ],
)
def test_sentence_boundaries_handle_realistic_punctuation_without_tiny_abbreviation_chunks(
    text, expected,
):
    assert sentence_texts(text) == expected


def test_subword_and_shared_unicode_offsets_keep_complete_original_source_slices():
    text = "İyi 🙂. Son söz."
    # Multiple tokenizer pieces may share one Unicode character's offsets.
    offsets = [(0, 1), (1, 3), (4, 5), (4, 5), (5, 6), (7, 10), (11, 14), (14, 15)]
    assert sentence_token_spans(text, offsets) == [(0, 5), (5, 8)]
    chunks = split_text(text, offsets, chunk_tokens=5, overlap_tokens=1, strategy="sentence")
    assert [chunk.text for chunk in chunks] == ["İyi 🙂.", "Son söz."]
    assert [(chunk.token_start, chunk.token_count) for chunk in chunks] == [(0, 5), (5, 3)]


def test_native_sentence_punctuation_can_split_without_whitespace_when_tokens_allow_it():
    text = "Risk yükseldi。Sonuç değişti。"
    offsets = [(index, index + 1) for index, character in enumerate(text) if not character.isspace()]
    assert sentence_texts(text, offsets) == ["Risk yükseldi。", "Sonuç değişti。"]


@pytest.mark.parametrize("budget", [1, 2, 3, 4, 7, 12])
def test_no_token_gaps_or_excess_budget_across_sentence_lengths_and_overlaps(budget):
    text = "Kısa. Çok daha uzun bir cümle, burada sınırı aşabilir. Orta cümle. Bitti!"
    for overlap in range(budget):
        chunks = split_text(
            text, whitespace_offsets(text), chunk_tokens=budget,
            overlap_tokens=overlap, strategy="sentence",
        )
        assert_coverage(text, chunks, budget, overlap)


def test_invalid_offsets_and_empty_sources_keep_same_contract_as_token_baseline():
    assert split_text("", [(0, 0)], chunk_tokens=4, overlap_tokens=0, strategy="sentence") == []
    text = "Alpha. Beta."
    offsets = [(0, 0), (0, 6), (7, 12), (-1, 2), (12, 19)]
    assert sentence_token_spans(text, offsets) == [(0, 1), (1, 2)]
    chunks = split_text(text, offsets, chunk_tokens=1, overlap_tokens=0, strategy="sentence")
    assert [chunk.text for chunk in chunks] == ["Alpha.", "Beta."]


def test_unknown_strategy_is_rejected_even_for_empty_source():
    with pytest.raises(ValueError, match="strategy"):
        split_text("", [], chunk_tokens=4, overlap_tokens=0, strategy="semantic")
