import { describe, expect, it } from "vitest";
import { FUSION_EXAMPLES, fusionRanking } from "./howItWorksData.js";

describe("the explainer's RRF example", () => {
  it("combines one-based ranks and includes candidates from either branch", () => {
    const rows = fusionRanking(FUSION_EXAMPLES[0], "hybrid");
    expect(rows.map((row) => row.id)).toEqual(["perps", "risk", "technical", "volatility", "volume"]);
    expect(rows[0].score).toBeCloseTo(1 / 62 + 1 / 61, 12);
    expect(rows.find((row) => row.id === "volume").score).toBeCloseTo(1 / 64, 12);
  });

  it("shows the selected branch's order without leaking other candidates", () => {
    for (const mode of ["dense", "bm25"]) {
      expect(fusionRanking(FUSION_EXAMPLES[0], mode).map((row) => row.id)).toEqual(FUSION_EXAMPLES[0][mode]);
    }
  });

  it("counts a duplicated candidate once and handles an empty branch", () => {
    const example = { documents: [{ id: "a" }, { id: "b" }], dense: ["a", "a", "b"], bm25: [] };
    const rows = fusionRanking(example, "hybrid");
    expect(rows[0].score).toBeCloseTo(1 / 61, 12);
    expect(rows[1].denseRank).toBe(2);
    expect(fusionRanking(example, "bm25")).toEqual([]);
  });

  it("rejects invalid ranking settings instead of displaying misleading scores", () => {
    expect(() => fusionRanking(FUSION_EXAMPLES[0], "unknown")).toThrow("Unknown retrieval mode");
    for (const constant of [-1, Infinity, NaN]) {
      expect(() => fusionRanking(FUSION_EXAMPLES[0], "hybrid", constant)).toThrow("Rank constant");
    }
  });
});
