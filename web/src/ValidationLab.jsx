import { useEffect, useMemo, useState } from "react";
import { fusionRanking } from "./howItWorksData.js";
import "./validationLab.css";

const DOCUMENTS = [
  { id: "A", title: "Bitcoin fiyat özeti", detail: "Fiyat var; ETF akışı yok." },
  { id: "B", title: "ETF net giriş tablosu", detail: "Soruya doğrudan kanıt sağlar." },
  { id: "C", title: "Ethereum ağ ücretleri", detail: "Farklı varlık ve konu." },
  { id: "D", title: "ETF akışlarının haftalık değişimi", detail: "Soruya doğrudan kanıt sağlar." },
];
export const VALIDATION_RANKINGS = { dense: ["A", "C", "B", "D"], bm25: ["D", "A", "C", "B"] };
VALIDATION_RANKINGS.hybrid = fusionRanking({ documents: DOCUMENTS, ...VALIDATION_RANKINGS }, "hybrid").map((row) => row.id);
const RANKINGS = VALIDATION_RANKINGS;

export function retrievalMetrics(ranking, relevantIds, k = 3) {
  const relevant = new Set(relevantIds);
  const uniqueRanking = [...new Set(ranking)];
  const hits = uniqueRanking.slice(0, k).filter((id) => relevant.has(id)).length;
  const first = uniqueRanking.findIndex((id) => relevant.has(id));
  return { hits, total: relevant.size, recall: relevant.size ? hits / relevant.size : null, reciprocalRank: first < 0 ? 0 : 1 / (first + 1), firstRank: first < 0 ? null : first + 1 };
}

// Mirrors trainer.py: a label ending ON the next boundary is also purged.
export function temporalCells(horizon = 1, size = 18) {
  const calibrationStart = Math.floor(size * 0.65);
  const holdoutStart = Math.floor(size * 0.80);
  return Array.from({ length: size }, (_, index) => {
    const period = index < calibrationStart ? "train" : index < holdoutStart ? "calibration" : "holdout";
    const boundary = period === "train" ? calibrationStart : holdoutStart;
    const purged = period !== "holdout" && index + horizon >= boundary;
    return { index, period, purged, labelEnd: index + horizon, boundary };
  });
}

function RagExperiment() {
  const [method, setMethod] = useState("dense");
  const [relevant, setRelevant] = useState(["B", "D"]);
  const [frozen, setFrozen] = useState(false);
  const [testOpen, setTestOpen] = useState(false);
  const [needsFreshTest, setNeedsFreshTest] = useState(false);
  const ranking = RANKINGS[method];
  const metrics = retrievalMetrics(ranking, relevant);
  const toggleRelevant = (id) => setRelevant((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  const reset = () => { if (testOpen) setNeedsFreshTest(true); setFrozen(false); setTestOpen(false); };
  return <article className="vl-card vl-rag" aria-labelledby="vl-rag-title">
    <header><span className="how-small-label">01 / RAG DENEYİ</span><h3 id="vl-rag-title">Önce ayar seç. Sonra test aç.</h3><span className="vl-demo">Temsili veriler · canlı benchmark değil</span></header>
    <div className="vl-split-flow">
      <div className={frozen ? "vl-window is-done" : "vl-window is-active"}><b>DEV</b><span>Ayar seçimi</span><small>{frozen ? "Ayar donduruldu" : "Değiştirebilirsin"}</small></div>
      <span className="vl-flow-arrow" aria-hidden="true">→</span>
      <div className={`vl-window ${testOpen ? "is-active" : "is-locked"}`}><b>TEST</b><span>Final ölçüm</span><small>{testOpen ? "Yalnız evaluation" : "Kilitli"}</small></div>
    </div>
    <div className="vl-controls" role="group" aria-label="Dev arama ayarı">
      {Object.keys(RANKINGS).map((item) => <button key={item} onClick={() => setMethod(item)} disabled={frozen} aria-pressed={method === item}>{item === "hybrid" ? "Hibrit" : item === "bm25" ? "BM25" : "Dense"}</button>)}
    </div>
    <p className="vl-query">Soru: “Bitcoin ETF akışları nasıl değişti?”</p>
    <div className="vl-ranking-head"><span>GETİRİLEN SIRA · RECALL İÇİN İLK 3</span><span>İNSAN ETİKETİ: İLGİLİ</span></div>
    <ol className="vl-documents">
      {ranking.map((id, index) => {
        const doc = DOCUMENTS.find((item) => item.id === id);
        return <li key={id} className={`${index < 3 ? "in-top-k" : "outside-k"} ${relevant.includes(id) ? "is-relevant" : ""}`}>
          <span className="vl-rank">{index + 1}</span><div><b>{id} · {doc.title}</b><small>{doc.detail}</small></div>
          <label><input type="checkbox" checked={relevant.includes(id)} disabled={frozen} onChange={() => toggleRelevant(id)} /><span className="vl-sr-only">{doc.title} ilgili kaynak</span></label>
        </li>;
      })}
    </ol>
    <div className="vl-metrics" aria-live="polite" aria-atomic="true">
      <div><span>DEV · Recall@3</span><strong>{metrics.recall === null ? "—" : metrics.recall.toFixed(2)}</strong><small>{metrics.hits} / {metrics.total} ilgili kaynak bulundu</small></div>
      <div><span>DEV · MRR, tek soru</span><strong>{metrics.reciprocalRank.toFixed(2)}</strong><small>{metrics.firstRank ? `1 / ${metrics.firstRank} · ilk ilgili sıra` : "İlgili kaynak yok"}</small></div>
    </div>
    <div className="vl-controls vl-actions"><button onClick={() => setFrozen(true)} disabled={frozen || !relevant.length}>1. Ayarı ve etiketleri dondur</button><button onClick={() => setTestOpen(true)} disabled={!frozen || testOpen}>2. Final ölçümü aç</button>{frozen && <button onClick={reset}>Yeni deney</button>}</div>
    <div className={`vl-message ${testOpen ? "is-open" : ""}`} role="status">
      {testOpen ? "Final test artık yalnız ölçüm içindir. Bu örnekte ayrı test soruları yok; final başarı skoru üretilmez." : frozen ? "Dev ayarı sabit. Bağımsız test sorularını son ölçüm için şimdi açabilirsin." : "Etiket kutularını değiştir: formüller yeniden hesaplanır. Test sonucu ayar seçimine geri taşınmaz."}
    </div>
    {needsFreshTest && <p className="vl-fresh-test">TEST → DEV × · Test açıldıktan sonra yeni ayar seçersen, yeni bağımsız test soruları gerekir.</p>}
    <p className="vl-footnote">Sıralamalar temsili; hibritin üstün olduğu sonucu çıkarılmaz. Çok soruda MRR, her sorunun 1 / ilk ilgili sıra değerinin ortalamasıdır.</p>
  </article>;
}

const PHASES = [
  { title: "Sınırları belirle", text: "Aynı tarihteki örnekler birlikte kalır. Gelecek getiri etiketi sınırı aşan veya sınıra değen hücreler çıkarılır." },
  { title: "Model fit", text: "Erken dönemde purged walk-forward ile model seçilir; seçilen model yalnız temiz train satırlarına fit edilir." },
  { title: "Calibrator fit", text: "Model sabit kalır. Ayrı kalibrasyon döneminin tahminleri ve gerçek etiketleriyle olasılık düzeltmesi öğrenilir." },
  { title: "Evaluation only", text: "Model ve kalibratör sabit. En son holdout yalnız tahmin ve metrik üretir; bu etiketler hiçbir fit adımına dönmez." },
];
const PERIODS = { train: { name: "MODEL", role: "model fit", phase: 1 }, calibration: { name: "KALİBRASYON", role: "calibrator fit", phase: 2 }, holdout: { name: "FINAL HOLDOUT", role: "evaluation only", phase: 3 } };

function TimeExperiment({ reducedMotion }) {
  const [horizon, setHorizon] = useState(1);
  const [phase, setPhase] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selected, setSelected] = useState(10);
  const cells = useMemo(() => temporalCells(horizon), [horizon]);
  const calibrationCount = cells.filter((cell) => cell.period === "calibration" && !cell.purged).length;
  const sample = cells[selected];
  useEffect(() => {
    if (!playing || reducedMotion || phase === 3 || (phase === 2 && !calibrationCount)) return undefined;
    const timer = setTimeout(() => {
      if (document.hidden) { setPlaying(false); return; }
      setPhase((value) => value + 1);
    }, 2800);
    return () => clearTimeout(timer);
  }, [playing, phase, reducedMotion, calibrationCount]);
  useEffect(() => { if (phase === 3 || reducedMotion || (phase === 2 && !calibrationCount)) setPlaying(false); }, [phase, reducedMotion, calibrationCount]);
  const changeHorizon = (value) => { setHorizon(value); setPhase(0); setPlaying(false); };
  return <article className="vl-card vl-time" aria-labelledby="vl-time-title">
    <header><span className="how-small-label">02 / ZAMAN SERİSİ DENEYİ</span><h3 id="vl-time-title">Gelecek etiketi sınırı geçemez.</h3><span className="vl-demo">18 temsili zaman hücresi</span></header>
    <div className="vl-controls"><span>İleri getiri ufku:</span>{[1, 3].map((value) => <button key={value} aria-pressed={horizon === value} onClick={() => changeHorizon(value)}>{value} hücre</button>)}<span className="vl-time-direction">Geçmiş → Gelecek</span></div>
    <div className="vl-time-scroll"><div className="vl-timeline" role="group" aria-label="18 zaman hücresi, hücre seçerek etiket ufkunu incele">
      {cells.map((cell) => <button key={cell.index} onClick={() => setSelected(cell.index)} aria-pressed={selected === cell.index} aria-label={`${cell.index + 1}. hücre, ${PERIODS[cell.period].name}${cell.purged ? ", purge: fit dışında" : ""}`} className={`vl-cell ${cell.period} ${cell.purged ? "is-purged" : ""} ${phase === PERIODS[cell.period].phase && !cell.purged ? "is-processing" : ""} ${cell.index >= selected && cell.index <= sample.labelEnd ? "in-label-window" : ""}`}><b>{cell.index + 1}</b><span>{cell.purged ? "×" : "·"}</span></button>)}
    </div></div>
    <div className="vl-sample" aria-live="polite"><code>t{selected + 1} → t{sample.labelEnd + 1}</code><span>{sample.purged ? `Etiket t${sample.boundary + 1} sınırına ulaşıyor: purge, fit'e girmez.` : sample.period === "holdout" ? "Final dönem: etiket yalnız değerlendirmede kullanılır." : "Etiket dönemin içinde: bu örnek fit'e girebilir."}</span></div>
    <div className="vl-fit-lanes">
      {Object.entries(PERIODS).map(([key, period]) => <div key={key} className={`vl-fit-lane ${key} ${phase === period.phase && (key !== "calibration" || calibrationCount) ? "is-active" : ""}`}><span className="vl-lane-count">{cells.filter((cell) => cell.period === key && !cell.purged).length} hücre</span><b>{period.name}</b><i aria-hidden="true">↓</i><strong>{period.role}</strong><small>{key === "holdout" ? "Fit'e geri dönüş yok" : key === "calibration" ? "Model ağırlıkları sabit" : "Model seçimi + son fit"}</small></div>)}
    </div>
    <div className="vl-phase" aria-live="polite" aria-atomic="true"><span>{String(phase + 1).padStart(2, "0")} / 04</span><div><b>{!calibrationCount && phase === 2 ? "Kalibrasyon: örnek kalmadı" : PHASES[phase].title}</b><p>{!calibrationCount && phase >= 2 ? "Bu ufukta kalibrasyon hücresi kalmadı. Gerçek eğitim durur; kalibratör veya final başarı metriği üretilemez." : PHASES[phase].text}</p></div></div>
    <div className="vl-controls vl-actions"><button disabled={reducedMotion || (phase === 2 && !calibrationCount)} onClick={() => { if (phase === 3) setPhase(0); setPlaying(!playing); }}>{playing ? "Duraklat" : phase === 3 ? "Yeniden oynat" : "Akışı oynat"}</button><button disabled={phase === 3 || (phase === 2 && !calibrationCount)} onClick={() => { setPlaying(false); setPhase(phase + 1); }}>Sonraki adım →</button><button onClick={() => { setPhase(0); setPlaying(false); }}>Başa dön</button></div>
    <p className="vl-footnote">%65 / %80 tarih sınırları backend protokolünü izler. Hücreler eğitseldir; gerçek eğitimde en az 30 kalibrasyon ve 30 final satır gerekir. {reducedMotion && "Hareket azaltma açık; adımları düğmeyle ilerlet."}</p>
  </article>;
}

export default function ValidationLab({ reducedMotion: motionPreference }) {
  const [systemReducedMotion, setSystemReducedMotion] = useState(() => typeof window !== "undefined" && Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches));
  useEffect(() => {
    const media = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!media) return undefined;
    const update = () => setSystemReducedMotion(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return <section className="validation-lab" aria-labelledby="validation-lab-title"><div className="how-section-heading"><div><span className="how-eyebrow">03 / DENEYİN MEKANİĞİ</span><h2 id="validation-lab-title" tabIndex={-1}>Öğrenmek ayrı. Ölçmek ayrı.</h2></div><span className="how-demo-tag">Etkileşimli protokol</span></div><p className="how-section-copy">İnsan etiketi ilgili kaynağı tanımlar; yanıt değerlendirmesi iddianın desteğini, finansal değerlendirme gelecek getiriyi ölçer. Bu üç ölçüm birbirinin başarı skoru değildir.</p><div className="vl-experiments"><RagExperiment /><TimeExperiment reducedMotion={motionPreference ?? systemReducedMotion} /></div></section>;
}
