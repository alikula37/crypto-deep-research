import { describe, expect, it } from "vitest";
import { ARCHITECTURE_EDGES, ARCHITECTURE_NODES, architectureDetail } from "./architectureMapData.js";
import { chunksForStrategy, claimsForChunks, retrievalForStrategy } from "./ragWalkthroughData.js";
import { fusionRanking } from "./howItWorksData.js";

function stateFor({ strategy = "sentence", chunkSize = 240, overlap = 40, rerank = false, topK = 3 } = {}) {
  const chunks = chunksForStrategy(strategy, chunkSize, overlap);
  const candidates = chunksForStrategy(strategy, 240, 40);
  const demo = retrievalForStrategy(strategy);
  const rows = fusionRanking({ documents: candidates, dense: demo.dense, bm25: demo.bm25 }, "hybrid");
  const finalRows = rerank ? demo.reranked.map((id) => rows.find((row) => row.id === id)) : rows;
  return { strategy, chunkSize, overlap, chunks, candidates, demo, rows, rerank, contexts: finalRows.slice(0, topK) };
}

const detail = (id, state, kind = "node") => architectureDetail({ kind, id }, state);
const example = (value) => value.example.map((item) => item.value).join("\n");

describe("inspectable architecture contracts", () => {
  it("joins persisted stores to both query branches without implying reindexing on each question", () => {
    const nodes = new Map(ARCHITECTURE_NODES.map((node) => [node.id, node]));
    expect(nodes.size).toBe(ARCHITECTURE_NODES.length);
    expect(new Set(ARCHITECTURE_EDGES.map((edge) => edge.id)).size).toBe(ARCHITECTURE_EDGES.length);
    for (const edge of ARCHITECTURE_EDGES) {
      expect(nodes.has(edge.from)).toBe(true);
      expect(nodes.has(edge.to)).toBe(true);
      expect(edge.phase).toBeGreaterThanOrEqual(0);
      expect(edge.phase).toBeLessThanOrEqual(6);
      if (nodes.get(edge.from).lane === "query") expect(nodes.get(edge.to).lane).toBe("query");
    }
    const persistedInputs = ARCHITECTURE_EDGES.filter((edge) => nodes.get(edge.from).lane === "index" && nodes.get(edge.to).lane === "query");
    expect(persistedInputs.map(({ from, to }) => [from, to])).toEqual([["lance", "dense"], ["sqlite", "bm25"]]);
    expect(ARCHITECTURE_EDGES.filter((edge) => edge.from === "question").map((edge) => edge.to)).toEqual(["queryEmbedding", "bm25"]);
    expect(nodes.get("chunk").phase).toBe(1);
    expect(nodes.get("rerank").optional).toBe(true);
    expect(nodes.get("answer").optional).toBe(true);
  });

  it("can explain every exposed box and arrow without an undefined runtime value", () => {
    const state = stateFor();
    for (const [kind, items] of [["node", ARCHITECTURE_NODES], ["edge", ARCHITECTURE_EDGES]]) {
      for (const item of items) {
        const explanation = detail(item.id, state, kind);
        expect(explanation.phase).toBe(item.phase);
        expect(explanation.description).toBeTruthy();
        expect(explanation.input).toBeTruthy();
        expect(explanation.output).toBeTruthy();
        expect(`${example(explanation)}\n${explanation.note}`).not.toMatch(/undefined|NaN/);
      }
    }
    expect(() => detail("missing-node", state)).toThrow("Unknown architecture selection");
  });

  it("shows the recorded rank constant and rank contributions used in the actual fusion result", () => {
    for (const strategy of ["sentence", "token"]) {
      const state = stateFor({ strategy });
      const constant = state.demo.provenance.rankConstant;
      expect(constant).toBe(60);
      for (const row of state.rows) {
        const denseRank = state.demo.dense.indexOf(row.id) + 1;
        const bm25Rank = state.demo.bm25.indexOf(row.id) + 1;
        expect(row.score).toBeCloseTo((denseRank ? 1 / (constant + denseRank) : 0) + (bm25Rank ? 1 / (constant + bm25Rank) : 0), 12);
      }
      const first = state.rows[0];
      const proof = detail("rrf", state);
      expect(example(proof)).toContain(`1/(${constant}+${first.denseRank}) + 1/(${constant}+${first.bm25Rank}) = ${first.score.toFixed(6)}`);
      expect(proof.note).toContain(`Rank sabiti ${constant}`);
      expect(detail("dense-rrf", state, "edge").note).toContain(`1/(${constant}+rank)`);
      const missing = state.rows.find((row) => !row.bm25Rank);
      expect(missing).toBeTruthy();
      expect(missing.score).toBeCloseTo(1 / (constant + missing.denseRank), 12);
    }
  });

  it("updates the chunking example while keeping the retrieval example on its recorded 240/40 index", () => {
    for (const strategy of ["sentence", "token"]) {
      const original = stateFor({ strategy });
      const adjusted = stateFor({ strategy, chunkSize: 48, overlap: 0 });
      expect(adjusted.chunks[0].end).not.toBe(adjusted.candidates[0].end);
      expect(example(detail("chunk", adjusted))).toContain("bütçe 48 · overlap ≤0");
      expect(example(detail("chunk", adjusted))).toContain(`C1 [0, ${adjusted.chunks[0].end})`);
      expect(detail("chunk", adjusted).note).toContain("240/40");
      for (const id of ["chunkEmbedding", "lance", "dense", "bm25", "rrf", "context"]) {
        expect(detail(id, adjusted)).toEqual(detail(id, original));
      }
      expect(example(detail("chunk-chunkEmbedding", adjusted, "edge"))).toContain(`C1 [0, ${adjusted.candidates[0].end})`);
    }
  });

  it("keeps reranking optional and reassigns citations to the selected top-k context", () => {
    for (const strategy of ["sentence", "token"]) {
      const original = stateFor({ strategy, topK: 2 });
      const reranked = stateFor({ strategy, rerank: true, topK: 2 });
      expect(example(detail("rerank", original))).toContain(original.rows.map((row) => row.id).join(" → "));
      expect(example(detail("rerank", reranked))).toContain(reranked.demo.reranked.join(" → "));
      expect(detail("rerank", reranked).note).toContain("cross-encoder çalıştırılmadı");
      const claim = claimsForChunks(original.candidates)[0];
      for (const state of [original, reranked]) {
        const index = state.contexts.findIndex((chunk) => claim.sourceIDs.includes(chunk.id));
        expect(example(detail("answer", state))).toContain(`[${index + 1}] ${state.contexts[index].id}:`);
        expect(example(detail("context-answer", state, "edge"))).toContain(`[${index + 1}] → ${state.contexts[index].id} →`);
      }
      const narrowed = stateFor({ strategy, rerank: true, topK: 1 });
      expect(example(detail("answer", narrowed))).toContain("Destekleyen pasaj bağlama alınmadı");
      expect(detail("context", narrowed).note).toContain("Demo top-1");
      expect(detail("context", narrowed).note).toContain("varsayılanı k=8");
      expect(detail("answer", narrowed).note).toContain("LLM çağrısı değildir");
    }
  });
});
