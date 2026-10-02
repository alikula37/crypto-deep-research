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
export function buildChunks(tokens, chunkTokens, overlapTokens, sourceText = DEMO_SOURCE.text) {
  if (!Number.isInteger(chunkTokens) || chunkTokens < 1) {
    throw new Error("chunkTokens must be a positive integer");
  }
  if (!Number.isInteger(overlapTokens) || overlapTokens < 0 || overlapTokens >= chunkTokens) {
    throw new Error("overlapTokens must satisfy 0 <= overlapTokens < chunkTokens");
  }
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

// Real measured ranks for the fixed default corpus only. When showing 48/8 or
// another window size, do not label these ranks as a fresh retrieval result.
// The parent may override excerpts with current chunks, but must retain the
// "önceden hesaplanmış 240/40 sıralaması" label in that teaching view.
export const RETRIEVAL_DEMO = {
  ...fixture.retrieval,
  label: fixture.retrieval.provenance.label,
  rerankerLabel: "Temsili yeniden sıralama · cross-encoder çalıştırılmadı",
  vectorLabel: "Gerçek embedding’in ilk 8 koordinatı · bir görselleştirme izdüşümü değildir",
};

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
// Claims refer to immutable DEFAULT 240/40 chunks. Citation numbers must be
// assigned from the currently selected top-3 order, never hardcoded: reranking
// changes [1]/[2]. For other window sizes show extractive current-chunk text,
// or withhold this answer; do not attribute these quotes to a different C1/C2.
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
      sourceIDs: ["C1"],
      quote: "Fonlamanın yüksek olması tek başına fiyatın düşeceğini kanıtlamaz.",
    },
    {
      id: "margin-risk",
      text: "Likidasyon riskini yorumlamak için kaldıraç oranı, teminat ve pozisyon büyüklüğü birlikte değerlendirilmelidir.",
      sourceIDs: ["C2"],
      quote: "Likidasyon riski; kaldıraç oranına, teminata ve pozisyon büyüklüğüne bağlıdır.",
    },
  ],
  unsupportedQuestion: "Bitcoin yarın tam olarak hangi fiyata düşecek?",
  abstention: "Bu kaynaklarda yarının fiyatını belirleyen bir bilgi yok; kesin bir seviye veremem.",
};

// Instructions match backend RAGEngine.answer_prompt. A real generation call
// is optional and requires OpenRouter configuration. The sandbox makes none.
export const DEMO_PROMPT_INSTRUCTIONS = "Aşağıdaki kaynaklara dayanarak soruyu Turkce, kaynak numaralarina atif yaparak yanitla.\nBilgi yoksa bunu açıkça belirt, uydurma.";
