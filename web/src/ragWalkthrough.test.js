import { describe, expect, it } from "vitest";
import { ANSWER_DEMO, DEMO_SOURCE, RETRIEVAL_DEMO, buildChunks, fuseDemoRanks } from "./ragWalkthroughData.js";
import { contextCitation, tokenRangeText } from "./RagWalkthrough.jsx";
import { retrievalMetrics, temporalCells, VALIDATION_RANKINGS } from "./ValidationLab.jsx";

describe("reproducible RAG walkthrough", () => {
  it("matches the Python-generated chunk boundaries and original excerpts", () => {
    const chunks = buildChunks(DEMO_SOURCE.tokens, 240, 40);
    expect(chunks).toHaveLength(5);
    for (const [index, chunk] of chunks.entries()) {
      const measured = RETRIEVAL_DEMO.documents[index];
      expect(chunk.start).toBe(measured.tokenStart);
      expect(chunk.tokenCount).toBe(measured.tokenCount);
      expect(chunk.text).toBe(measured.excerpt);
      expect(tokenRangeText(DEMO_SOURCE, chunk.start, chunk.end)).toBe(chunk.text);
    }
    expect(chunks.at(-1).end).toBe(DEMO_SOURCE.tokens.length);
  });

  it.each([[48, 0], [48, 8], [120, 20], [240, 40], [240, 80]])("preserves full coverage at %i / %i and exact overlaps", (size, overlap) => {
    const chunks = buildChunks(DEMO_SOURCE.tokens, size, overlap);
    const covered = new Set(chunks.flatMap((chunk) => Array.from({ length: chunk.tokenCount }, (_, index) => chunk.start + index)));
    expect(covered.size).toBe(DEMO_SOURCE.tokens.length);
    for (let index = 1; index < chunks.length; index += 1) {
      expect(chunks[index - 1].end - chunks[index].start).toBe(overlap);
    }
  });

  it("matches backend-measured RRF, including a missing BM25 candidate", () => {
    const fused = fuseDemoRanks();
    expect(fused.map((row) => row.id)).toEqual(RETRIEVAL_DEMO.fused.map((row) => row.id));
    fused.forEach((row, index) => expect(row.score).toBeCloseTo(RETRIEVAL_DEMO.fused[index].score, 12));
    expect(fused.find((row) => row.id === "C5").bm25Rank).toBeUndefined();
  });

  it("keeps authored claims in their actual source and reassigns citations after reranking", () => {
    const chunks = buildChunks(DEMO_SOURCE.tokens, 240, 40);
    for (const claim of ANSWER_DEMO.claims) {
      expect(chunks.find((chunk) => chunk.id === claim.sourceIDs[0]).text).toContain(claim.quote);
    }
    const fused = fuseDemoRanks().slice(0, 3);
    const reranked = RETRIEVAL_DEMO.reranked.slice(0, 3).map((id) => chunks.find((chunk) => chunk.id === id));
    expect(contextCitation("C2", fused)).toBe(3);
    expect(contextCitation("C2", reranked)).toBe(1);
    expect(contextCitation("C2", fused.slice(0, 1))).toBeNull();
  });

  it("rejects chunk windows that cannot advance", () => {
    for (const [size, overlap] of [[0, 0], [48, 48], [48, -1], [48.5, 8]]) {
      expect(() => buildChunks(DEMO_SOURCE.tokens, size, overlap)).toThrow();
    }
  });
});

describe("validation teaching mechanics", () => {
  it("derives the experiment hybrid order from the displayed branch ranks", () => {
    expect(VALIDATION_RANKINGS.hybrid).toEqual(["A", "D", "C", "B"]);
    expect(retrievalMetrics(VALIDATION_RANKINGS.hybrid, ["B", "D"])).toMatchObject({ recall: 0.5, reciprocalRank: 0.5 });
  });
  it("distinguishes recall from reciprocal rank and avoids empty-label success", () => {
    expect(retrievalMetrics(["A", "C", "B", "D"], ["B", "D"])).toMatchObject({ hits: 1, total: 2, recall: 0.5, reciprocalRank: 1 / 3 });
    expect(retrievalMetrics(["B", "D", "A", "C"], ["B", "D"])).toMatchObject({ recall: 1, reciprocalRank: 1 });
    expect(retrievalMetrics(["A", "B"], [])).toMatchObject({ recall: null, reciprocalRank: 0 });
  });

  it("purges labels that touch a future boundary and withholds calibration when none remain", () => {
    const short = temporalCells(1);
    expect(short[10]).toMatchObject({ period: "train", purged: true, labelEnd: 11, boundary: 11 });
    expect(short.filter((cell) => cell.period === "calibration" && !cell.purged)).toHaveLength(2);
    expect(temporalCells(3).filter((cell) => cell.period === "calibration" && !cell.purged)).toHaveLength(0);
    expect(temporalCells(3).filter((cell) => cell.period === "holdout").every((cell) => !cell.purged)).toBe(true);
  });
});
