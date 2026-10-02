import { useEffect, useMemo, useRef, useState } from "react";
import PipelineScene from "./PipelineScene.jsx";
import RagWalkthrough from "./RagWalkthrough.jsx";
import ValidationLab from "./ValidationLab.jsx";
import { FUSION_EXAMPLES, fusionRanking, INTERVIEW_SCRIPT, STAGES } from "./howItWorksData.js";
import { IconChart, IconCheck, IconCopy, IconDoc, IconPlay, IconSearch, IconSparkles } from "./icons.jsx";
import "./howItWorks.css";

function Arrow({ back = false }) {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" style={back ? { transform: "rotate(180deg)" } : undefined}><path d="M4 12h15M13 6l6 6-6 6" /></svg>;
}
function Pause() {
  return <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M3 2h3v12H3zM10 2h3v12h-3z" /></svg>;
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return reduced;
}

function usePageVisibility() {
  const [visible, setVisible] = useState(() => !document.hidden);
  useEffect(() => {
    const update = () => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  return visible;
}

function FusionExplorer({ onSearch }) {
  const [exampleIndex, setExampleIndex] = useState(0);
  const [retrieval, setRetrieval] = useState("hybrid");
  const example = FUSION_EXAMPLES[exampleIndex];
  const rows = useMemo(() => fusionRanking(example, retrieval), [example, retrieval]);
  return (
    <section className="how-fusion how-surface" aria-labelledby="fusion-title">
      <div className="how-section-heading">
        <div><span className="how-eyebrow">02 / ARAMANIN MANTIĞI</span><h2 id="fusion-title">Aynı soru. İki bakış açısı.</h2></div>
        <span className="how-demo-tag">Temsili örnek</span>
      </div>
      <p className="how-section-copy">Arama yöntemini değiştir; sonuç sırasının nasıl değiştiğini gör. Bu örnekler yöntemi anlatır, canlı sorgu çalıştırmaz.</p>
      <div className="how-fusion-layout">
        <div className="how-query-panel">
          <span className="how-small-label">ÖRNEK SORU</span>
          <div className="how-query"><IconSearch width={20} height={20} /><p>{example.query}</p></div>
          <div className="how-query-options" role="group" aria-label="Örnek soru seçimi">
            {FUSION_EXAMPLES.map((item, index) => <button key={item.id} aria-pressed={exampleIndex === index} onClick={() => setExampleIndex(index)}>{index === 0 ? "Likidasyon riski" : "ETH / BTC paritesi"}</button>)}
          </div>
          <div className="how-retrieval-switch" role="group" aria-label="Örnek arama yöntemi">
            {[["dense", "Dense", "Anlam"], ["bm25", "BM25", "Kelimeler"], ["hybrid", "Hibrit", "Birleşim"]].map(([key, label, note]) => <button key={key} aria-pressed={retrieval === key} onClick={() => setRetrieval(key)}><b>{label}</b><span>{note}</span></button>)}
          </div>
          <div className="how-formula">
            <span className="how-small-label">{retrieval === "hybrid" ? "RECIPROCAL RANK FUSION" : retrieval === "dense" ? "ANLAMSAL YAKINLIK" : "SÖZCÜKSEL EŞLEŞME"}</span>
            {retrieval === "hybrid" ? <><code>RRF(d) = Σ 1 / (60 + sıraᵢ(d))</code><p>Skorlar farklı ölçekte olabilir. RRF, skor büyüklüklerini değil iki listenin sıralarını birleştirir.</p></> : <p>{retrieval === "dense" ? "Benzer anlamlar, farklı kelimelerle anlatılmış olsa da bulunabilir. Soru embedding’i, kayıtlı vektörlerle karşılaştırılır." : "Ticker, özel isim ve belirli terimler sözcüksel aramada belirleyicidir. SQLite FTS5, sonuçları BM25 ile sıralar."}</p>}
          </div>
          <button className="how-text-link" onClick={() => onSearch(example.query)}>Bu soruyu gerçek kaynaklarda ara <Arrow /></button>
        </div>
        <div className="how-ranking" aria-live="polite" aria-atomic="true">
          <div className="how-ranking-head"><span>KAYNAK SIRALAMASI</span><span>{retrieval === "hybrid" ? "RRF skoru" : "Liste sırası"}</span></div>
          {rows.map((doc, index) => <div className="how-result" key={doc.id}>
            <span className="how-result-rank">{String(index + 1).padStart(2, "0")}</span>
            <div><b>{doc.title}</b><span>{doc.kind}<i />Dense #{doc.denseRank || "—"}<i />BM25 #{doc.bm25Rank || "—"}</span></div>
            <strong>{retrieval === "hybrid" ? doc.score.toFixed(4) : `#${index + 1}`}</strong>
          </div>)}
          <div className="how-ranking-note"><IconCheck width={15} height={15} /><span>Hibritin faydası varsayılmaz; dense, BM25 ve hibrit aynı etiketli sorgularda kıyaslanır.</span></div>
        </div>
      </div>
    </section>
  );
}

function ValidationPanel() {
  return <section className="how-validation" aria-labelledby="validation-title">
    <div className="how-section-heading"><div><span className="how-eyebrow">03 / UYGULANMIŞ DENEYLER</span><h2 id="validation-title">Öğretim şemasından, gerçek ölçüme.</h2></div></div>
    <div className="how-metric-grid" style={{ marginTop: 20 }}>
      <article className="how-metric-card"><span className="how-small-label how-cyan">RAG PİLOTU · 2 EKİM 2026</span><h3>107 kaynak · 5 test sorusu</h3><p className="how-section-copy">Hibrit arama, ilgili kaynağı 4/5 soruda ilk beşte buldu. HitRate@5 = 0,80. Etiketler asistan taslağıdır ve insan incelemesi bekler; bu küçük pilot genel başarı kanıtı değildir. İnsan etiketleriyle yanıt kalitesi sonucu henüz yok.</p></article>
      <article className="how-metric-card"><span className="how-small-label how-gold">FİNANSAL MODEL · 2 EKİM 2026</span><h3>7.400 satır · üç model reddedildi</h3><p className="how-section-copy">1 / 7 / 30 günlük modeller ayrı final holdout'ta baseline Brier skorunu geçemedi. Kalite kapıları üç modeli de reddetti; hiçbiri aktifleştirilmedi. AUC / Brier / ECE, RAG kalitesi olarak sunulmaz.</p></article>
    </div>
    <div className="how-experiment-note"><span className="how-status-dot" /><div><b>Kaynaklar ve deney protokolü açık.</b><p>Öğretim sahnesindeki örnekler ile bu ölçümler farklı veri setleridir. Deney notları yöntem, kapsam ve sınırlamaları kaydeder.</p></div><a href="https://github.com/alikula37/crypto-deep-research/tree/main/docs/experiments" target="_blank" rel="noreferrer">Deney notları <Arrow /></a></div>
  </section>;
}

export default function HowItWorks({ onNavigate, onSearch, health }) {
  const reducedMotion = useReducedMotion();
  const visible = usePageVisibility();
  const [mode, setMode] = useState(() => new URLSearchParams(window.location.search).get("mode") === "interview" ? "interview" : "guide");
  const [activeStep, setActiveStep] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [touring, setTouring] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const pageRef = useRef(null);
  const [fullscreen, setFullscreen] = useState(false);
  const stage = STAGES[activeStep];
  const interview = mode === "interview";

  useEffect(() => {
    const url = new URL(window.location.href);
    if (mode === "interview") url.searchParams.set("mode", "interview");
    else url.searchParams.delete("mode");
    window.history.replaceState(null, "", url);
  }, [mode]);
  useEffect(() => {
    if (!touring || !playing || reducedMotion || !visible) return undefined;
    const timer = setTimeout(() => {
      if (activeStep === STAGES.length - 1) setTouring(false);
      else setActiveStep(activeStep + 1);
    }, 12000);
    return () => clearTimeout(timer);
  }, [touring, playing, reducedMotion, visible, activeStep]);
  useEffect(() => {
    const update = () => setFullscreen(document.fullscreenElement === pageRef.current);
    document.addEventListener("fullscreenchange", update);
    return () => document.removeEventListener("fullscreenchange", update);
  }, []);
  useEffect(() => {
    if (!copied) return undefined;
    const timer = setTimeout(() => setCopied(false), 2500);
    return () => clearTimeout(timer);
  }, [copied]);

  const selectStep = (index) => { setActiveStep(index); setTouring(false); };
  const startTour = () => { setActiveStep(0); setPlaying(true); setTouring(true); };
  const copyScript = async () => {
    try { await navigator.clipboard.writeText(INTERVIEW_SCRIPT); setCopied(true); setCopyError(false); }
    catch { setCopyError(true); }
  };
  const toggleFullscreen = async () => {
    try {
      if (document.fullscreenElement === pageRef.current) await document.exitFullscreen();
      else await pageRef.current.requestFullscreen();
    } catch { /* The browser may restrict fullscreen; all controls stay available inline. */ }
  };

  return (
    <div className="how-page" ref={pageRef} data-mode={mode}>
      <header className="how-hero">
        <div><span className="how-eyebrow"><span className="how-status-dot" /> NASIL ÇALIŞIR?</span><h1>{interview ? <>Sistem, <em>içeriden.</em></> : <>Veriyi gör.<br /><em>Mantığı anla.</em></>}</h1><p>{interview ? "Metnin parçalanmasını, iki aramanın birleşmesini ve iddianın kanıta bağlanmasını gör. Her adımda girdiyi, dönüşümü ve çıktıyı incele." : "Bir araştırmanın nasıl oluştuğunu ve bir sorunun doğru kaynağa nasıl ulaştığını adım adım keşfet."}</p></div>
        <div className="how-hero-aside"><div className="how-mode-switch" role="group" aria-label="Anlatım modu"><button aria-pressed={!interview} onClick={() => setMode("guide")}><IconDoc width={15} height={15} />Ürün turu</button><button aria-pressed={interview} onClick={() => setMode("interview")}><IconSparkles width={15} height={15} />Mülakat modu</button></div><p>{interview ? "Mimari kararlar, deney tasarımı ve savunulabilir sonuçlar." : "İlk araştırmandan kaynaklı sorulara, kullanım rehberin."}</p><div className="how-facts"><span><b>10</b> analiz modülü</span><span><b>66</b> kriter</span><span><b>2</b> arama yöntemi</span></div>{interview && document.fullscreenEnabled && <button className="how-interview-present" onClick={toggleFullscreen}>{fullscreen ? "Sunumdan çık" : "Sunum ekranı"}</button>}</div>
      </header>

      {interview ? <RagWalkthrough reducedMotion={reducedMotion} visible={visible} onNavigate={onNavigate} onSearch={onSearch} /> : <>
      <section className="how-architecture how-surface" aria-label="Etkileşimli sistem turu">
        <div className="how-architecture-main"><div className="how-scene-heading"><span className="how-eyebrow">01 / VERİNİN YOLCULUĞU</span><span className="how-demo-tag">Kavram turu</span></div>
          <PipelineScene activeStep={activeStep} onSelectStep={selectStep} playing={playing} reducedMotion={reducedMotion} mode={mode} />
          <p className="how-scene-caption">Araştırma ve soru-cevap ayrı çalışır. Her araştırma bir RAG sorgusu başlatmaz.</p>
          <ol className="how-stage-list" aria-label="Sistem aşamaları">{STAGES.map((item, index) => <li key={item.label}><button aria-pressed={activeStep === index} onClick={() => selectStep(index)} style={{ "--stage-color": item.color }}><span className="how-stage-no">0{index + 1}</span><b>{item.label}</b><span>{item.short}</span></button></li>)}</ol>
          <div className="how-playback"><span><i className={playing && !reducedMotion ? "how-motion-dot is-playing" : "how-motion-dot"} />{reducedMotion ? "Hareket azaltma tercihi açık" : touring ? playing ? "60 saniyelik tur sürüyor" : "Tur duraklatıldı" : playing ? "Noktalara tıkla, akışı keşfet" : "Animasyon duraklatıldı"}</span><div><button onClick={() => setPlaying(!playing)} disabled={reducedMotion} aria-label={playing ? "Animasyonu duraklat" : "Animasyonu oynat"}>{playing ? <Pause /> : <IconPlay width={12} height={12} />}{playing ? "Duraklat" : "Oynat"}</button><button onClick={startTour} disabled={reducedMotion || touring}><IconPlay width={10} height={10} />60 sn tur</button>{document.fullscreenEnabled && <button onClick={toggleFullscreen}>{fullscreen ? "Sunumdan çık" : "Sunum ekranı"}</button>}</div></div>
        </div>
        <div className="how-stage-detail" style={{ "--stage-color": stage.color }}>
          <div className="how-detail-top"><span className="how-small-label">{stage.noun}</span><span className="how-detail-index">0{activeStep + 1}<span> / 05</span></span></div>
          <div className="how-detail-copy" key={`${activeStep}-${mode}`}><h2>{stage.title}</h2><p>{interview ? stage.technical : stage.description}</p><div className="how-tech-tags">{stage.tags.map((tag) => <span key={tag}>{tag}</span>)}</div><div className="how-insight"><span className="how-small-label">{interview ? "MÜLAKATTA SORULABİLİR" : "KULLANIRKEN"}</span>{interview ? <><b>{stage.question}</b><p>{stage.answer}</p></> : <p>{stage.takeaway}</p>}</div></div>
          <div className="how-detail-navigation"><button aria-label="Önceki aşama" disabled={activeStep === 0} onClick={() => selectStep(activeStep - 1)}><Arrow back /></button><button aria-label="Sonraki aşama" disabled={activeStep === 4} onClick={() => selectStep(activeStep + 1)}><Arrow /></button><button className="how-text-link" onClick={() => onNavigate(stage.tab)}>{stage.action} <Arrow /></button></div>
        </div>
      </section>

      <div className="how-two-paths"><div><span>ARAŞTIRMA</span><p>Kaynaklar <Arrow /> 10 modül + 66 kriter <Arrow /><b>Rapor ve prompt</b></p></div><div><span>SORU-CEVAP</span><p>Kayıtlı kaynaklar <Arrow /> Hibrit arama <Arrow /><b>Kaynak bağlamı + opsiyonel LLM</b></p></div></div>

      <FusionExplorer onSearch={onSearch} />
      </>}

      {interview ? <><ValidationLab reducedMotion={reducedMotion} /><ValidationPanel /><section className="how-interview-script how-surface"><div className="how-section-heading"><div><span className="how-eyebrow">04 / 90 SANİYEDE PROJE</span><h2>“Nasıl yaptım?” kadar “Nasıl ölçtüm?”</h2></div><button onClick={copyScript}><IconCopy width={14} height={14} />{copied ? "Kopyalandı" : "Anlatımı kopyala"}</button></div><blockquote>{INTERVIEW_SCRIPT}</blockquote>{copyError && <p role="status">Panoya erişilemedi. Anlatım metnini seçerek kopyalayabilirsin.</p>}</section></> : <section className="how-quickstart" aria-labelledby="quickstart-title"><div className="how-section-heading"><div><span className="how-eyebrow">03 / ŞİMDİ SEN DENE</span><h2 id="quickstart-title">İlk araştırman, üç adımda.</h2></div></div><div className="how-quickstart-grid">{[["01", "Bir varlık seç", "Üstte varlığı ve profili seç. Derin Araştırma ile kaynaklı raporunu oluştur.", "overview", "Araştırmaya git", IconChart], ["02", "Kanıtları oku", "Bulgular’da Tam / Kısmi / Veri yok durumlarına, güvene ve kaynaklara bak.", "findings", "Bulguları aç", IconDoc], ["03", "Bir soru sor", "Kaynak Arama’da geçmiş araştırmalarına soru sor; bulunan pasajları incele.", "rag", "Kaynak aramayı aç", IconSearch]].map(([number, title, text, tab, action, Icon]) => <article key={number}><div><span>{number}</span><Icon width={20} height={20} /></div><h3>{title}</h3><p>{text}</p><button className="how-text-link" onClick={() => onNavigate(tab)}>{action}<Arrow /></button></article>)}</div></section>}

      <footer className="how-page-footer"><span><span className="how-status-dot" />Yerel metin ve vektör depolama · Dış veri sağlayıcıları · Opsiyonel model yanıtı</span><span>{health ? health.openrouter ? "OpenRouter yanıt üretimi yapılandırılmış" : "Bu kurulumda OpenRouter anahtarı yok; arama ve prompt kullanılabilir" : "Model yanıtı için OpenRouter yapılandırılır"}</span></footer>
    </div>
  );
}
