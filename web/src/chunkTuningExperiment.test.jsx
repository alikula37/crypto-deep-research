import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import ChunkTuningExperiment from "./ChunkTuningExperiment.jsx";
import summary from "./fixtures/chunk-tuning-summary.json";
import report from "../../docs/experiments/datasets/2026-10-chunk-tuning-results.json";
import { chunksForStrategy } from "./ragWalkthroughData.js";

describe("recorded chunk selection experiment", () => {
  it("shows measured values from the backend report and retains the dev-only limitation", () => {
    expect(summary.corpus.sha256).toBe(report.corpus.sha256);
    expect(summary.selection).toEqual(report.selection);
    expect(summary.runs).toEqual(report.runs.map(({ key, settings, metrics, index, cost }) => ({ key, settings, metrics, index, cost })));
    expect(summary.test_evaluated).toBe(false);
    const html = renderToStaticMarkup(<ChunkTuningExperiment onInspect={() => {}} />);
    expect(html).toContain("Etiketler asistan taslağı");
    expect(html).toContain("ürün varsayılanı 240/40 korunuyor");
    expect(html).not.toMatch(/<details[^>]*\sopen(?:=|>)/);
  });
  it("can inspect every measured budget without changing the recorded retrieval fixture", () => {
    for (const { settings } of summary.runs) {
      const chunks = chunksForStrategy(settings.strategy, settings.chunk_tokens, settings.overlap_tokens);
      expect(chunks[0].start).toBe(0);
      expect(chunks.at(-1).end).toBe(910);
      expect(chunks.every((chunk) => chunk.tokenCount <= settings.chunk_tokens)).toBe(true);
    }
  });
});
