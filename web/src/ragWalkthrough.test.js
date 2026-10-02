import { describe, expect, it } from "vitest";
import { ANSWER_DEMO, DEMO_SOURCE, RETRIEVAL_DEMO, SENTENCE_RETRIEVAL_DEMO, SENTENCE_SPANS, SENTENCE_EXAMPLES, buildChunks, buildSentenceChunks, chunksForStrategy, claimsForChunks, fuseDemoRanks } from "./ragWalkthroughData.js";
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
    for (const claim of claimsForChunks(chunks)) {
      expect(chunks.find((chunk) => chunk.id === claim.sourceIDs[0]).text).toContain(claim.quote);
    }
    const fused = fuseDemoRanks().slice(0, 3);
    const reranked = RETRIEVAL_DEMO.reranked.slice(0, 3).map((id) => chunks.find((chunk) => chunk.id === id));
    expect(contextCitation("C2", fused)).toBe(3);
    expect(contextCitation("C2", reranked)).toBe(1);
    expect(contextCitation("C2", fused.slice(0, 1))).toBeNull();
  });

  it("matches every Python-generated sentence packer example and original excerpt", () => {
    expect(SENTENCE_EXAMPLES.length).toBeGreaterThan(0);
    for (const example of SENTENCE_EXAMPLES) {
      const chunks = buildSentenceChunks(DEMO_SOURCE.tokens, example.chunkTokens, example.overlapTokens);
      expect(chunks.map((chunk) => ({ tokenStart: chunk.start, tokenCount: chunk.tokenCount, excerpt: chunk.text }))).toEqual(example.chunks);
    }
  });

  it.each([[48, 0], [48, 8], [120, 20], [240, 40], [240, 80]])("preserves complete coverage and bounded whole-sentence overlap at %i / %i", (size, overlap) => {
    const chunks = buildSentenceChunks(DEMO_SOURCE.tokens, size, overlap);
    const covered = new Set(chunks.flatMap((chunk) => Array.from({ length: chunk.tokenCount }, (_, index) => chunk.start + index)));
    expect(covered.size).toBe(DEMO_SOURCE.tokens.length);
    expect(chunks.every((chunk) => chunk.tokenCount <= size)).toBe(true);
    for (let index = 1; index < chunks.length; index += 1) {
      const actual = chunks[index - 1].end - chunks[index].start;
      expect(actual).toBeGreaterThanOrEqual(0);
      expect(actual).toBeLessThanOrEqual(overlap);
      if (actual) {
        expect(SENTENCE_SPANS.some((span) => span.start === chunks[index].start)).toBe(true);
        expect(SENTENCE_SPANS.some((span) => span.end === chunks[index - 1].end)).toBe(true);
      }
    }
  });

  it("uses the matching measured retrieval snapshot and full quotation sources for either strategy", () => {
    for (const [strategy, demo] of [["token", RETRIEVAL_DEMO], ["sentence", SENTENCE_RETRIEVAL_DEMO]]) {
      const chunks = chunksForStrategy(strategy, 240, 40);
      expect(chunks.map((chunk) => chunk.text)).toEqual(demo.documents.map((doc) => doc.excerpt));
      const fused = fuseDemoRanks(demo);
      expect(fused.map((row) => row.id)).toEqual(demo.fused.map((row) => row.id));
      fused.forEach((row, index) => expect(row.score).toBeCloseTo(demo.fused[index].score, 12));
      const claims = claimsForChunks(chunks);
      for (const claim of claims) {
        expect(claim.sourceIDs).toHaveLength(1);
        expect(chunks.find((chunk) => chunk.id === claim.sourceIDs[0]).text).toContain(claim.quote);
      }
      const riskClaim = claims.find((claim) => claim.id === "margin-risk");
      const reranked = demo.reranked.map((id) => chunks.find((chunk) => chunk.id === id));
      expect(contextCitation(riskClaim.sourceIDs[0], reranked)).toBe(1);
      expect(claimsForChunks([]).every((claim) => claim.sourceIDs.length === 0)).toBe(true);
    }
  });

  it("keeps the hard token budget when one sentence is longer than a chunk", () => {
    const text = "aa bb cc dd ee ff gg hh ii jj";
    const tokens = Array.from(text.matchAll(/\S+/g), (match, index) => ({ index, start: match.index, end: match.index + match[0].length }));
    const chunks = buildSentenceChunks(tokens, 4, 2, [{ start: 0, end: 10 }], text);
    expect(chunks.map((chunk) => [chunk.start, chunk.end])).toEqual([[0, 4], [4, 8], [8, 10]]);
    expect(chunks.every((chunk) => chunk.hasFallback && chunk.overlapCount === 0)).toBe(true);
    expect(chunks.map((chunk) => chunk.text).join(" ")).toBe(text);
  });

  it("drops carried sentences when the next new sentence needs the token budget", () => {
    const text = "a b c d e f g h i j k";
    const tokens = Array.from(text.matchAll(/\S+/g), (match, index) => ({ index, start: match.index, end: match.index + 1 }));
    const chunks = buildSentenceChunks(tokens, 5, 4, [{ start: 0, end: 2 }, { start: 2, end: 4 }, { start: 4, end: 9 }, { start: 9, end: 11 }], text);
    expect(chunks.map((chunk) => [chunk.start, chunk.end])).toEqual([[0, 4], [4, 9], [9, 11]]);
    expect(buildSentenceChunks([], 5, 1, [], "")).toEqual([]);
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
