import fixture from "./fixtures/rag-demo-tokens.json";

// Teaching corpus only. Token pieces are real multilingual-e5-large tokenizer
// output. Dense/BM25 ranks were computed in scratch backend stores at 240/40.
// Neither this module nor its controls change application settings or run search.
export const DEMO_SOURCE = {
  id: fixture.id,
  title: fixture.title,
  url: fixture.url,
  source: fixture.source,
  text: fixture.text,
  label: fixture.label,
  tokenizerLabel: fixture.tokenizerLabel,
  tokenizer: fixture.tokenizer,
  tokenCount: fixture.tokenCount,
  // start/end are UTF-16 character offsets, compatible with String.slice.
  // text is the exact source slice; token is the tokenizer's subword spelling.
  tokens: fixture.tokens,
};

export const DEMO_QUERY = fixture.retrieval.query;
export const SENTENCE_SPANS = fixture.sentenceSpans || [];
export const SENTENCE_EXAMPLES = fixture.sentenceExamples || [];

export const CHUNK_STRATEGIES = {
  sentence: { label: "Cümle sınırları", detail: "Tam cümleleri token bütçesine sığdır" },
  token: { label: "Sabit token · baseline", detail: "Boyut ve overlap kadar kes" },
};

export const CHUNK_PRESETS = [
  { id: "default", label: "Varsayılan · 240 / 40", chunkTokens: 240, overlapTokens: 40 },
  { id: "teaching", label: "Yakından gör · 48 / 8", chunkTokens: 48, overlapTokens: 8 },
];

/** Mirrors backend rag.chunking.split_text's token-window/overlap algorithm.
 * Chunk start/end are TOKEN indices [start,end); charStart/charEnd are source
 * character offsets. A chunk's text always comes from the original full text.
 * No concatenation of token strings: that would lose original whitespace.
 * The final window stops at EOF instead of producing a redundant overlap tail.
 */
function validateChunkSettings(chunkTokens, overlapTokens) {
  if (!Number.isInteger(chunkTokens) || chunkTokens < 1) {
    throw new Error("chunkTokens must be a positive integer");
  }
  if (!Number.isInteger(overlapTokens) || overlapTokens < 0 || overlapTokens >= chunkTokens) {
    throw new Error("overlapTokens must satisfy 0 <= overlapTokens < chunkTokens");
  }
}

export function buildChunks(tokens, chunkTokens, overlapTokens, sourceText = DEMO_SOURCE.text) {
  validateChunkSettings(chunkTokens, overlapTokens);
  const offsets = tokens.filter(({ start, end }) => start >= 0 && start < end && end <= sourceText.length);
  const chunks = [];
  let start = 0;
  while (start < offsets.length) {
    const end = Math.min(start + chunkTokens, offsets.length);
    const charStart = offsets[start].start;
    const charEnd = offsets[end - 1].end;
    chunks.push({
      id: `C${chunks.length + 1}`,
      start,
      end,
      tokenStart: start,
      tokenCount: end - start,
      overlapCount: chunks.length ? Math.min(overlapTokens, end - start) : 0,
      charStart,
      charEnd,
      text: sourceText.slice(charStart, charEnd),
    });
    if (end === offsets.length) break;
    start = end - overlapTokens;
  }
  return chunks;
}

/** Mirrors backend sentence packing, using Python-generated token spans.
 * Oversized sentences fall back to disjoint budget-sized token fragments.
 * Only a contiguous suffix of complete sentences can be carried as overlap.
 * Drop the oldest overlap sentence if it leaves no room for the next new unit.
 */
export function buildSentenceChunks(tokens, chunkTokens, overlapTokens, spans = SENTENCE_SPANS, sourceText = DEMO_SOURCE.text) {
  validateChunkSettings(chunkTokens, overlapTokens);
  const offsets = tokens.filter(({ start, end }) => start >= 0 && start < end && end <= sourceText.length);
  if (!offsets.length) return [];
  if (!spans.length || spans[0].start !== 0 || spans.at(-1).end !== offsets.length || spans.some((span, index) => span.end <= span.start || (index && span.start !== spans[index - 1].end))) {
    throw new Error("Sentence spans must partition all valid tokens");
  }
  const units = spans.flatMap(({ start, end }) => {
    if (end - start <= chunkTokens) return [{ start, end, whole: true }];
    const fragments = [];
    for (let cursor = start; cursor < end; cursor += chunkTokens) {
      fragments.push({ start: cursor, end: Math.min(cursor + chunkTokens, end), whole: false });
    }
    return fragments;
  });
  const chunks = [];
  let cursor = 0;
  let carry = [];
  while (cursor < units.length) {
    while (carry.length && units[cursor].end - carry[0].start > chunkTokens) carry.shift();
    const packed = [...carry];
    const start = carry[0]?.start ?? units[cursor].start;
    while (cursor < units.length && units[cursor].end - start <= chunkTokens) {
      packed.push(units[cursor]);
      cursor += 1;
    }
    const end = packed.at(-1).end;
    const charStart = offsets[start].start;
    const charEnd = offsets[end - 1].end;
    chunks.push({
      id: `C${chunks.length + 1}`, start, end, tokenStart: start, tokenCount: end - start,
      overlapCount: chunks.length ? Math.max(0, chunks.at(-1).end - start) : 0,
      charStart, charEnd, text: sourceText.slice(charStart, charEnd),
      hasFallback: packed.some((unit) => !unit.whole),
      endsAtSentenceBoundary: spans.some((span) => span.end === end),
    });
    carry = [];
    for (let index = packed.length - 1; index >= 0; index -= 1) {
      const unit = packed[index];
      if (!unit.whole || end - unit.start > overlapTokens) break;
      carry.unshift(unit);
    }
  }
  return chunks;
}

export function chunksForStrategy(strategy, chunkTokens, overlapTokens) {
  if (strategy === "sentence") return buildSentenceChunks(DEMO_SOURCE.tokens, chunkTokens, overlapTokens);
  if (strategy === "token") return buildChunks(DEMO_SOURCE.tokens, chunkTokens, overlapTokens);
  throw new Error("Unknown chunk strategy");
}

// Measured ranks exist separately for each strategy at fixed 240/40 settings.
// Teaching controls for another budget do not alter either retrieval snapshot.
const retrievalDemo = (retrieval) => ({
  ...retrieval,
  label: retrieval.provenance.label,
  rerankerLabel: "Temsili yeniden sıralama · cross-encoder çalıştırılmadı",
  vectorLabel: "Gerçek embedding’in ilk 8 koordinatı · bir görselleştirme izdüşümü değildir",
});
export const RETRIEVAL_DEMO = retrievalDemo(fixture.retrieval);
export const SENTENCE_RETRIEVAL_DEMO = fixture.sentenceRetrieval ? retrievalDemo(fixture.sentenceRetrieval) : null;

export function retrievalForStrategy(strategy) {
  if (strategy === "token") return RETRIEVAL_DEMO;
  if (strategy === "sentence" && SENTENCE_RETRIEVAL_DEMO) return SENTENCE_RETRIEVAL_DEMO;
  throw new Error("Measured snapshot is unavailable for this chunk strategy");
}

/** Same RRF as backend: ignore duplicates inside each list, sum 1/(60+rank),
 * and break equal scores by source ID. Missing BM25 candidates remain missing.
 * Raw dense distances and BM25 scores are deliberately not added together.
 */
export function fuseDemoRanks(demo = RETRIEVAL_DEMO, rankConstant = 60) {
  if (!Number.isFinite(rankConstant) || rankConstant < 0) {
    throw new Error("rankConstant must be non-negative");
  }
  const documents = new Map(demo.documents.map((doc) => [doc.id, doc]));
  const merged = new Map();
  for (const [branch, ids] of [["dense", demo.dense], ["bm25", demo.bm25]]) {
    const seen = new Set();
    let rank = 0;
    for (const id of ids) {
      if (seen.has(id)) continue;
      seen.add(id);
      rank += 1;
      if (!documents.has(id)) continue;
      const current = merged.get(id) || { ...documents.get(id), score: 0 };
      current.score += 1 / (rankConstant + rank);
      current[`${branch}Rank`] = rank;
      merged.set(id, current);
    }
  }
  return [...merged.values()].sort((a, b) => b.score - a.score || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

// Authored answer, not an OpenRouter output or faithfulness measurement.
// Claims resolve to the first measured chunk containing their full quotation.
// Citation numbers follow the selected context order. Changing the strategy or
// reranking must resolve sources again rather than reusing token-baseline IDs.
export const ANSWER_DEMO = {
  label: "Yazılmış örnek yanıt · LLM çağrısı değildir",
  defaultChunkOnly: true,
  chunkTokens: 240,
  overlapTokens: 40,
  contextLimit: 3,
  claims: [
    {
      id: "funding-alone",
      text: "Yüksek fonlama, fiyatın düşeceğini tek başına kanıtlamaz.",
      quote: "Fonlamanın yüksek olması tek başına fiyatın düşeceğini kanıtlamaz.",
    },
    {
      id: "margin-risk",
      text: "Likidasyon riskini yorumlamak için kaldıraç oranı, teminat ve pozisyon büyüklüğü birlikte değerlendirilmelidir.",
      quote: "Likidasyon riski; kaldıraç oranına, teminata ve pozisyon büyüklüğüne bağlıdır.",
    },
  ],
  unsupportedQuestion: "Bitcoin yarın tam olarak hangi fiyata düşecek?",
  abstention: "Bu kaynaklarda yarının fiyatını belirleyen bir bilgi yok; kesin bir seviye veremem.",
};

export function claimsForChunks(chunks) {
  return ANSWER_DEMO.claims.map((claim) => ({
    ...claim,
    sourceIDs: chunks.filter((chunk) => chunk.text.includes(claim.quote)).slice(0, 1).map((chunk) => chunk.id),
  }));
}

// Instructions match backend RAGEngine.answer_prompt. A real generation call
// is optional and requires OpenRouter configuration. The sandbox makes none.
export const DEMO_PROMPT_INSTRUCTIONS = "Aşağıdaki kaynaklara dayanarak soruyu Turkce, kaynak numaralarina atif yaparak yanitla.\nBilgi yoksa bunu açıkça belirt, uydurma.";
