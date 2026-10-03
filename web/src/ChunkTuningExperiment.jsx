import { useRef, useState } from "react";
import experiment from "./fixtures/chunk-tuning-summary.json";
import "./chunkTuningExperiment.css";

const experimentDate = new Date(experiment.created_at).toLocaleDateString("tr-TR", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
const percent = (value) => `${(value * 100).toFixed(1)}%`;

export default function ChunkTuningExperiment({ onInspect }) {
  const [selectedKey, setSelectedKey] = useState(experiment.selection.candidate);
  const panelRef = useRef(null);
  const selected = experiment.runs.find((run) => run.key === selectedKey);
  const recommendation = experiment.runs.find((run) => run.key === experiment.selection.candidate);
  return <details className="chunk-tuning-experiment" ref={panelRef}>
    <summary><span>Boyutu nasıl seçiyoruz?</span><small>{experiment.runs.length} ayar · {experiment.n_queries} geliştirme sorusu · ölçülen deney</small></summary>
    <div className="chunk-tuning-content">
      <p><b>Model sınırı: {experiment.embedding.input_limit} token.</b> E5’in sınırı aşılmaz. Aynı {experiment.corpus.sources} kaynak, her ayarda yeniden parçalanıp ayrı indekste aranır. Önce kanıtın bulunmasına, sonra getirilen metin miktarına bakılır.</p>
      <div className="chunk-tuning-table-wrap"><table><caption>{experimentDate} · kaydedilmiş dev ölçümü · ilk {experiment.k} chunk · hybrid / reranker kapalı</caption><thead><tr><th scope="col">Boyut / overlap</th><th scope="col">Kanıt kapsamı</th><th scope="col">Kaynak recall</th><th scope="col">nDCG</th><th scope="col">Bağlam tokenı</th><th scope="col">Vektör sayısı</th></tr></thead><tbody>{experiment.runs.map((run) => <tr key={run.key} data-selected={selectedKey === run.key}><th scope="row"><button aria-pressed={selectedKey === run.key} onClick={() => setSelectedKey(run.key)}>{run.settings.chunk_tokens} / {run.settings.overlap_tokens}{run.key === experiment.selection.candidate ? <span>dev önerisi</span> : run.key === experiment.selection.baseline ? <span>varsayılan</span> : null}</button></th><td>{percent(run.metrics.evidence_coverage)}</td><td>{percent(run.metrics.recall)}</td><td>{run.metrics.ndcg.toFixed(3)}</td><td>{Math.round(run.cost.mean_context_tokens)}</td><td>{run.index.vectors}</td></tr>)}</tbody></table></div>
      <div className="chunk-tuning-selection" aria-live="polite"><div><b>{selected.settings.chunk_tokens} / {selected.settings.overlap_tokens}</b><span>Kanıt metinlerinin {percent(selected.metrics.evidence_coverage)}’i ilk {experiment.k} parçada tam olarak bulundu.</span></div><button onClick={() => { panelRef.current.open = false; onInspect(selected.settings.chunk_tokens, selected.settings.overlap_tokens); }}>Kurgu belgede sınırlarını gör →</button></div>
      <p className="chunk-tuning-caveat"><b>Dev önerisi: {recommendation.settings.chunk_tokens}/{recommendation.settings.overlap_tokens}.</b> Önce kanıt kapsamı, kaynak recall ve nDCG; her aşamada 2 yüzde puan tolerans. Kalanlarda daha az bağlam tokenı tercih edilir. Etiketler asistan taslağı, insan incelemesi bekliyor. Test açılmadı; ürün varsayılanı 240/40 korunuyor. Bu sonuç kesin optimum veya yanıt doğruluğu değildir.</p>
      <p className="chunk-tuning-definitions">Kanıt kapsamı: etiketli metnin tek bir getirilen chunk içinde bulunması. Kaynak recall: ilgili belgelerin bulunma oranı. nDCG: ilgili kaynakların üst sıralarda olması. Token miktarı E5 ile sayılır; LLM ücret hesabı değildir. Ürün bağlamı varsayılan 8 chunk; nihai seçim bu kesimde de doğrulanmalı. Laboratuvar düğmesi yalnız aşağıdaki kurgu belgeyi değiştirir.</p>
      <a href="https://github.com/alikula37/crypto-deep-research/blob/codex/interactive-how-it-works/docs/experiments/2026-10-chunk-tuning.md" target="_blank" rel="noreferrer">Deney, seçim kuralı ve sınırlamalar ↗</a>
    </div>
  </details>;
}
