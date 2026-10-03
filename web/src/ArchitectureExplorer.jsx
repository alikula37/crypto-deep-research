import { useRef, useState } from "react";
import { ARCHITECTURE_NODES, ARCHITECTURE_EDGES, architectureDetail } from "./architectureMapData.js";
import "./architectureExplorer.css";

const BOXES = {
  source: [20, 45, 350, 55], chunk: [20, 135, 350, 55],
  chunkEmbedding: [20, 225, 165, 55], sqlite: [205, 225, 165, 55], lance: [20, 315, 165, 55],
  question: [445, 45, 400, 55], queryEmbedding: [445, 135, 185, 55],
  dense: [445, 225, 185, 55], bm25: [660, 225, 185, 55],
  rrf: [445, 315, 400, 55], rerank: [445, 395, 400, 55],
  context: [445, 475, 400, 55], answer: [445, 555, 400, 55],
};
const WIRES = {
  "source-chunk": ["M195 100 V135", 195, 117],
  "chunk-chunkEmbedding": ["M102 190 V225", 102, 207],
  "chunk-sqlite": ["M287 190 V225", 287, 207],
  "chunkEmbedding-lance": ["M102 280 V315", 102, 297],
  "lance-dense": ["M185 342 H407 Q417 342 417 332 V262 Q417 252 427 252 H445", 350, 342],
  "sqlite-bm25": ["M287 280 V286 Q287 292 297 292 H742 Q752 292 752 282 V280", 350, 292],
  "question-queryEmbedding": ["M538 100 V135", 538, 117],
  "question-bm25": ["M752 100 V225", 752, 164],
  "queryEmbedding-dense": ["M538 190 V225", 538, 207],
  "dense-rrf": ["M538 280 V297 Q538 303 548 303 H578 Q588 303 588 313 V315", 535, 299],
  "bm25-rrf": ["M752 280 V297 Q752 303 742 303 H712 Q702 303 702 313 V315", 758, 299],
  "rrf-rerank": ["M645 370 V395", 645, 383],
  "rerank-context": ["M645 450 V475", 645, 463],
  "context-answer": ["M645 530 V555", 645, 543],
};

function NodeButton({ node, selection, onSelect, badge, mobile = false }) {
  const [x, y, w, h] = BOXES[node.id];
  return <button className={`arch-node arch-node-${node.id}`} data-lane={node.lane}
    data-store={node.id === "sqlite" || node.id === "lance"} data-optional={!!node.optional}
    aria-label={`${node.title}: ayrıntıları göster`} aria-pressed={selection.kind === "node" && selection.id === node.id}
    onClick={() => onSelect({ kind: "node", id: node.id })}
    style={mobile ? undefined : { left: `${x / 9}%`, top: y, width: `${w / 9}%`, minHeight: h }}>
    <span>{node.kicker}{node.optional && <em>opsiyonel</em>}</span><b>{node.displayTitle || node.title}</b>
    <small>{badge || node.subtitle}</small>
  </button>;
}

export default function ArchitectureExplorer({ model, onInspect, onNavigate, onValidate, reducedMotion }) {
  const [selection, setSelection] = useState({ kind: "node", id: "chunk" });
  const [mobileLane, setMobileLane] = useState("index");
  const detailRef = useRef(null);
  const detail = architectureDetail(selection, model);
  const currentChunk = model.chunks[0];
  const badges = {
    source: `Tam metin · ${model.chunks.at(-1).end} token`,
    chunk: `${model.strategy === "sentence" ? "Cümle sınırları" : "Sabit token"} · C1: ${currentChunk.tokenCount}/${model.chunkSize} · ≤${model.overlap}`,
    question: "Belge indeksini yeniden kurmaz",
    rrf: model.rows.map((row) => row.id).join(" → "),
    rerank: model.rerank ? "Temsili yeniden sıralama açık" : "Kapalı · RRF sırası korunur",
    context: `top-${model.contexts.length}: ${model.contexts.map((row) => row.id).join(" · ")}`,
    answer: "Demo LLM çağrısı yapmaz · üründe OpenRouter",
  };
  const select = (next) => setSelection(next);
  const scrollDetail = () => {
    detailRef.current?.scrollIntoView({ block: "start", behavior: reducedMotion ? "auto" : "smooth" });
    detailRef.current?.focus({ preventScroll: true });
  };
  const related = (edge) => selection.kind === "edge" ? selection.id === edge.id : edge.from === selection.id || edge.to === selection.id;
  const labelFor = (edge) => `${ARCHITECTURE_NODES.find((node) => node.id === edge.from).title} → ${ARCHITECTURE_NODES.find((node) => node.id === edge.to).title}: ${edge.label}`;

  return <section className="architecture-explorer how-surface" aria-labelledby="architecture-explorer-title">
    <header className="arch-heading"><div><span className="how-eyebrow">01 / SİSTEMİN TAM HARİTASI</span><h2 id="architecture-explorer-title" tabIndex={-1}>Belge bir kez indekslenir.<br />Her soru kanıtı yeniden seçer.</h2></div><p>Bir kutuya tıkla: görevini gör.<br />Okun etiketine tıkla: taşınan veriyi gör.</p></header>
    <div className="arch-report-path" aria-label="Araştırma raporunun oluşumu"><span>RAPOR ÜRETİMİ</span><b>Dış veri + haber</b><i>→</i><button onClick={() => onNavigate("findings")}>10 modül · 66 kriter</button><i>→</i><button onClick={() => onNavigate("report")}>Yerel rapor + prompt</button><i>→</i><b>Yeni belge olarak indeksle ↓</b></div>
    <div className="arch-layout">
      <div className="arch-map-area">
        <div className="arch-lane-switch" role="group" aria-label="Mobil mimari akışı"><button aria-pressed={mobileLane === "index"} onClick={() => setMobileLane("index")}>01 · Belge geldiğinde</button><button aria-pressed={mobileLane === "query"} onClick={() => setMobileLane("query")}>02 · Soru geldiğinde</button></div>
        <button className="arch-mobile-detail-link" onClick={scrollDetail}>Seçilen: {detail.title} · detay ↓</button>
        <div className="arch-board" aria-label="Belge indeksleme ve soru yanıt akış haritası">
          <div className="arch-lane-bg arch-index-bg"><span>01 / BELGE GELDİĞİNDE</span><p>Yeni veya değişen kaynak</p></div>
          <div className="arch-lane-bg arch-query-bg"><span>02 / SORU GELDİĞİNDE</span><p>Mevcut iki indeks üzerinden</p></div>
          <svg className="arch-wires" viewBox="0 0 900 630" preserveAspectRatio="none" aria-hidden="true"><defs><marker id="architecture-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 1 L8 5 L0 9" fill="none" stroke="#a1bfaf" strokeWidth="1.5" /></marker></defs>{ARCHITECTURE_EDGES.map((edge) => <g key={edge.id} className={`${related(edge) ? "is-related" : ""} ${edge.id === "lance-dense" || edge.id === "sqlite-bm25" ? "is-persistent" : ""}`}><path className="arch-wire-hit" d={WIRES[edge.id][0]} onClick={() => select({ kind: "edge", id: edge.id })} /><path className="arch-wire" d={WIRES[edge.id][0]} markerEnd="url(#architecture-arrow)" /></g>)}</svg>
          {ARCHITECTURE_EDGES.map((edge) => <button key={edge.id} className="arch-edge" aria-label={labelFor(edge)} aria-pressed={selection.kind === "edge" && selection.id === edge.id} data-related={related(edge)} onClick={() => select({ kind: "edge", id: edge.id })} style={{ left: `${WIRES[edge.id][1] / 9}%`, top: WIRES[edge.id][2] }}>{edge.label}</button>)}
          {ARCHITECTURE_NODES.map((node) => <NodeButton key={node.id} node={node} selection={selection} onSelect={select} badge={badges[node.id]} />)}
          <div className="arch-persistence-note"><b>İki depo, aynı chunk kimliği.</b><p>LanceDB vektörü tutar.<br />SQLite metni ve kaynak bilgisini tutar.</p><span>İndeksler sorgular arasında kalır.</span></div>
        </div>
        <div className="arch-mobile-board" aria-label={mobileLane === "index" ? "Belge indeksleme akışı" : "Soru ve yanıt akışı"}>
          {ARCHITECTURE_NODES.filter((node) => node.lane === mobileLane).map((node) => <div className="arch-mobile-step" key={node.id}>
            <NodeButton node={node} selection={selection} onSelect={select} badge={badges[node.id]} mobile />
            <div className="arch-mobile-handoffs">{ARCHITECTURE_EDGES.filter((edge) => edge.from === node.id).map((edge) => <button key={edge.id} aria-label={labelFor(edge)} aria-pressed={selection.kind === "edge" && selection.id === edge.id} onClick={() => select({ kind: "edge", id: edge.id })}>↓ {edge.label} <span>→ {ARCHITECTURE_NODES.find((item) => item.id === edge.to).title}</span></button>)}</div>
          </div>)}
          {mobileLane === "query" && <div className="arch-mobile-stores"><span>KALICI İNDEKSLERDEN GELEN VERİ</span>{ARCHITECTURE_EDGES.filter((edge) => edge.id === "lance-dense" || edge.id === "sqlite-bm25").map((edge) => <button key={edge.id} aria-label={labelFor(edge)} aria-pressed={selection.kind === "edge" && selection.id === edge.id} onClick={() => select({ kind: "edge", id: edge.id })}>{labelFor(edge)}</button>)}</div>}
        </div>
        <div className="arch-map-note"><span className="arch-note-dot" /><p><b>Çalışan mekanizma, kurgu belge.</b> Chunking kutusu canlı ayarı gösterir; arama hattı seçili yöntemin 240/40 indeksini kullanır. Embedding ve arama sıraları gerçek hesaplamalardır. Reranker sırası ve yanıt öğretim örneğidir.</p></div>
      </div>
      <aside className="arch-detail" ref={detailRef} tabIndex={-1} aria-label="Seçilen mimari öğesinin ayrıntısı">
        <span className="arch-detail-kicker">{selection.kind === "edge" ? "BAĞLANTI / TAŞINAN VERİ" : detail.kicker}</span>
        <h3>{detail.title}</h3><p>{detail.description}</p>
        <dl><div><dt>GİRDİ</dt><dd>{detail.input}</dd></div><div><dt>ÇIKTI</dt><dd>{detail.output}</dd></div></dl>
        <div className="arch-detail-example"><span>BU ÖRNEKTE</span>{detail.example.map((item) => <div key={item.label}><small>{item.label}</small><code>{item.value}</code></div>)}</div>
        <p className="arch-detail-note">{detail.note}</p>
        <button className="arch-inspect" onClick={() => onInspect(detail.phase)}>Bu adımı laboratuvarda incele <span>↓</span></button>
        <a href={`https://github.com/alikula37/crypto-deep-research/blob/8dea984/${detail.codePath}`} target="_blank" rel="noreferrer">Kodda karşılığı: {detail.codeLabel} ↗</a>
        <span className="arch-selection-status" role="status">Seçilen: {detail.title}</span>
      </aside>
    </div>
    <footer className="arch-validation-path"><div><span>AYRI ÖLÇÜM HATLARI</span><p><b>RAG:</b> kaynak bulma + atıf desteği <i>·</i> <b>Finansal ML:</b> walk-forward → kalibrasyon → final holdout</p></div><button onClick={onValidate}>Ölçüm notları ↓</button></footer>
  </section>;
}
