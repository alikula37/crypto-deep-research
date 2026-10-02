import { useEffect, useMemo, useState } from "react";
import RagMechanismScene from "./RagMechanismScene.jsx";
import { DEMO_SOURCE, DEMO_QUERY, RETRIEVAL_DEMO, ANSWER_DEMO, buildChunks } from "./ragWalkthroughData.js";
import { fusionRanking } from "./howItWorksData.js";
import { IconPlay, IconSearch, IconCheck } from "./icons.jsx";
import "./ragWalkthrough.css";

const PHASES = [
  { label: "Belge", title: "Tam metni sakla. Kaynağı kaybetme.", input: "Araştırma raporu", output: "Metin + kaynak kimliği", why: "Aranabilir parçalar değişebilir; kaynak metin yeniden indekslemek için korunur." },
  { label: "Chunking", title: "Sınırdaki bilgi, iki parçada da yaşar.", input: "Tokenizer offsetleri", output: "Örtüşen token pencereleri", why: "Boyut bağlamı, overlap ise tekrar miktarını belirler. İkisi de dev sorgularında ölçülerek seçilir." },
  { label: "Embedding", title: "Soru ve pasaj, aynı vektör uzayında.", input: "Chunk metni + soru", output: "Vektörler / iki ayrı indeks", why: "Vektör, anlam aramasını mümkün kılar. Tam metin aynı zamanda sözcüksel arama için saklanır." },
  { label: "İki arama", title: "Bir soru, iki bağımsız aday listesi.", input: "Soru", output: "Dense sırası + BM25 sırası", why: "Anlam ve birebir terim eşleşmesi farklı adayları öne çıkarabilir; ham skorları aynı ölçekte saymayız." },
  { label: "Fusion", title: "Her sıra, görünür bir katkıya dönüşür.", input: "İki sıralı liste", output: "RRF / opsiyonel yeniden sıralama", why: "Bir aday iki listede de bulunursa iki katkı alır. Cross-encoder varsa soru–pasaj çiftini birlikte değerlendirir." },
  { label: "Bağlam", title: "Modelin gördüğü kanıtı sen de gör.", input: "Seçilen top-k pasaj", output: "Numaralı kaynaklar + talimat", why: "LLM’e tüm arşiv gönderilmez; seçilen pasajların metni, kaynak bilgisi ve soru gönderilir." },
  { label: "Yanıt", title: "İddiadan, onu destekleyen pasaja git.", input: "Kaynaklı prompt", output: "İddia + atıf / bilgi yok", why: "Atıf yazılması doğruluk garantisi değildir. İddia ve kaynak desteği ayrıca insan etiketleriyle değerlendirilir." },
];

export function tokenRangeText(source, start, end) {
  if (end <= start || !source.tokens[start] || !source.tokens[end - 1]) return "";
  return source.text.slice(source.tokens[start].start, source.tokens[end - 1].end);
}

export function contextCitation(id, selected) {
  const index = selected.findIndex((item) => item.id === id);
  return index < 0 ? null : index + 1;
}

function Arrow() {
  return <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M3 12h17m-6-6 6 6-6 6" /></svg>;
}

function ArchitectureMap({ onNavigate }) {
  return <div className="rag-architecture-map" aria-label="Araştırma ve soru-cevap için ayrı çalışma hatları">
    <div><span className="rag-path-label">RAPOR ÜRETİMİ</span><span>Veri sağlayıcıları</span><Arrow /><button onClick={() => onNavigate("findings")}>10 modül · 66 kriter</button><Arrow /><button onClick={() => onNavigate("report")}>Yerel rapor + prompt</button><Arrow /><b>Bilgi tabanına kayıt ↓</b></div>
    <div><span className="rag-path-label">YENİ BELGE GELDİĞİNDE</span><span>Tam kaynak metni</span><Arrow /><b>Chunk → embedding → kalıcı indeks</b></div>
    <div><span className="rag-path-label">HER SORUDA</span><span>Soru → soru embedding'i</span><Arrow /><b>Arama → fusion → bağlam</b><Arrow /><span>Opsiyonel LLM yanıtı</span></div>
    <p>Araştırma raporu yapılandırılmış analizlerden oluşur. Belgeler kaydedilirken indekslenir; her soruda belge indeksini yeniden kurmayız.</p>
  </div>;
}

function SourcePanel() {
  return <div className="rag-source-panel">
    <div className="rag-document-title"><span>RAPOR / DEMO KAYNAĞI</span><h3>{DEMO_SOURCE.title}</h3><code>parent_id: {DEMO_SOURCE.id}</code></div>
    <div className="rag-source-text">{DEMO_SOURCE.text}</div>
    <div className="rag-storage-pair"><div><b>SQLite / kaynak arşivi</b><p>Tam metin, kaynak, tarih ve belge kimliği.</p></div><div><b>Sonraki adım: chunk’lar</b><p>Her parça, aynı <code>parent_id</code> ile kaynak belgeye bağlanır.</p></div></div>
  </div>;
}

function ChunkPanel({ chunkSize, overlap, setSettings, chunks, selectedId, setSelectedId }) {
  const selectedIndex = Math.max(0, chunks.findIndex((chunk) => chunk.id === selectedId));
  const current = chunks[selectedIndex];
  const next = chunks[selectedIndex + 1];
  const repeated = next ? Math.max(0, current.end - next.start) : 0;
  const total = chunks.reduce((sum, chunk) => sum + chunk.tokenCount, 0);
  const boundary = next?.start ?? current.end;
  const leftStart = Math.max(current.start, boundary - 12);
  const rightEnd = next ? Math.min(next.end, current.end + 12) : current.end;
  const shared = repeated ? tokenRangeText(DEMO_SOURCE, boundary, current.end) : "";
  const leftText = DEMO_SOURCE.text.slice(DEMO_SOURCE.tokens[leftStart].start, repeated ? DEMO_SOURCE.tokens[boundary].start : current.charEnd);
  const rightText = next ? DEMO_SOURCE.text.slice(current.charEnd, DEMO_SOURCE.tokens[rightEnd - 1].end) : "";
  const position = (token) => `${token / DEMO_SOURCE.tokens.length * 100}%`;
  return <div className="rag-chunk-lab">
    <div className="rag-chunk-controls">
      <div><span className="rag-small-label">PENCERE BOYUTU</span><div className="rag-preset-buttons">{[[48, 8, "48 / 8 · yakın görünüm"], [120, 20, "120 / 20"], [240, 40, "240 / 40 · sistem varsayılanı"]].map(([size, sharedTokens, label]) => <button key={size} aria-pressed={chunkSize === size && overlap === sharedTokens} onClick={() => setSettings(size, sharedTokens)}>{label}</button>)}</div></div>
      <label>Overlap <strong>{overlap} token</strong><input type="range" min="0" max={Math.min(80, chunkSize - 1)} value={overlap} onChange={(event) => setSettings(chunkSize, Number(event.target.value))} /></label>
    </div>
    <div className="rag-chunk-stats"><span><b>{chunks.length}</b> chunk</span><span><b>{chunkSize - overlap}</b> token ilerleme</span><span><b>{total - DEMO_SOURCE.tokens.length}</b> tekrar edilen token</span><span><b>%100</b> token kapsama</span></div>
    <div className="rag-token-ruler"><span>Token 0</span><span>{DEMO_SOURCE.tokens.length} · belgenin sonu</span></div>
    <div className="rag-window-strip" aria-label="Belge üzerindeki chunk sınırları">{chunks.slice(Math.max(0, selectedIndex - 2), Math.max(0, selectedIndex - 2) + 6).map((chunk) => <button key={chunk.id} aria-pressed={chunk.id === current.id} onClick={() => setSelectedId(chunk.id)} title={`${chunk.id}: [${chunk.start}, ${chunk.end})`}><span className="rag-window-range" style={{ left: position(chunk.start), width: position(chunk.end - chunk.start) }}><i style={{ width: `${Math.min(chunk.overlapCount, chunk.tokenCount) / chunk.tokenCount * 100}%` }} /><b>{chunk.id}</b></span><small>[{chunk.start}, {chunk.end})</small></button>)}</div>
    <div className="rag-chunk-picker" role="group" aria-label="Chunk seçimi">{chunks.map((chunk) => <button key={chunk.id} aria-pressed={chunk.id === current.id} onClick={() => setSelectedId(chunk.id)}>{chunk.id}</button>)}</div>
    <div className="rag-overlap-heading"><h3>{next ? `${current.id} sonu ↔ ${next.id} başı` : `${current.id} · son parça`}</h3><div><span className={repeated ? "rag-gold-tag" : "rag-muted-tag"}>{repeated ? `Aynı ${repeated} token, iki parçada` : "Ortak token yok"}</span><button disabled={!next} onClick={() => setSelectedId(next.id)}>Sonraki sınırı göster →</button></div></div>
    <div className="rag-boundary-pair"><article><span>{current.id} · son bölüm</span><p>{leftText}<mark>{shared}</mark></p><code>token_start={current.start} · token_count={current.tokenCount}</code></article><article><span>{next ? `${next.id} · ilk bölüm` : "Belge bitti"}</span><p>{next ? <><mark>{shared}</mark>{rightText}</> : "Son chunk için yeni bir pencere açılmaz."}</p><code>{next ? `next_start = ${current.end} − ${overlap} = ${next.start}` : "end = belge token sayısı"}</code></article></div>
    <div className="rag-token-pieces"><span>Token ≠ kelime. Modelin gerçek alt-parçaları:</span><div>{DEMO_SOURCE.tokens.slice(Math.max(0, boundary - 4), Math.min(DEMO_SOURCE.tokens.length, boundary + 8)).map((token) => <code key={token.index} className={repeated && token.index >= boundary && token.index < current.end ? "shared" : ""}><small>{token.index}</small>{token.token}</code>)}</div></div>
    <div className="rag-experiment-note"><b>{overlap ? "Altın renkli metin birebir aynıdır." : "Overlap kapalı: sınır iki ayrı adayda kalır."}</b><span>Ayarlar bu öğretim belgesini yeniden böler. Sorgu turu, aşağıda belirtilen 240/40 indeksinin kaydedilmiş sonuçlarını kullanır.</span></div>
  </div>;
}

function EmbeddingPanel({ candidates, selectedId, setSelectedId }) {
  const chunk = candidates.find((item) => item.id === selectedId) || candidates[0];
  const vector = RETRIEVAL_DEMO.documents.find((item) => item.id === chunk.id)?.vectorPreview;
  const maxAbs = Math.max(...vector.map(Math.abs), Number.EPSILON);
  return <div className="rag-embedding-panel">
    <div className="rag-chunk-picker" role="group" aria-label="Vektörü incelenecek chunk">{candidates.map((item) => <button key={item.id} aria-pressed={chunk.id === item.id} onClick={() => setSelectedId(item.id)}>{item.id}</button>)}</div>
    <div className="rag-embedding-flow"><article><span className="rag-small-label">BELGE PARÇASI</span><b>{chunk.id} · {chunk.tokenCount} token</b><p>{chunk.text.slice(0, 230)}…</p></article><div className="rag-model-box"><b>FastEmbed / ONNX</b><span>{RETRIEVAL_DEMO.provenance.model}</span><Arrow /></div><article className="rag-vector-card"><span className="rag-small-label">CHUNK VEKTÖRÜ</span><div className="rag-vector-bars">{vector.slice(0, 8).map((value, index) => <i key={index} style={{ "--vector-height": `${Math.max(2, Math.abs(value) / maxAbs * 88)}%` }} className={value < 0 ? "negative" : ""} />)}</div><code>[{vector.slice(0, 8).map((value) => value.toFixed(3)).join(", ")}, …]</code><small>Gerçek embedding’in ilk 8 koordinatı · d={RETRIEVAL_DEMO.vectorDimension}. Çubuklar bu 8 koordinatın en büyük mutlak değerine göre ölçeklenir; işaret renkle gösterilir.</small></article></div>
    <div className="rag-query-embedding"><IconSearch width={18} height={18} /><div><span className="rag-small-label">SORU DA AYNI MODELLE EMBED EDİLİR</span><p>{DEMO_QUERY}</p></div><code>q → [{RETRIEVAL_DEMO.queryVectorPreview.map((value) => value.toFixed(3)).join(", ")}, …]</code></div>
    <div className="rag-storage-pair"><div><b>LanceDB → dense</b><p>Chunk kimliği + vektör. Sorunun vektörüyle yakınlık araması.</p></div><div><b>SQLite FTS5 → BM25</b><p>Aynı chunk kimliği + metin. Sözcüksel eşleşme ve sıralama.</p></div></div>
  </div>;
}

function RankedList({ label, note, ids, documents, onSelect, selectedId, scores }) {
  return <article className="rag-retrieval-lane"><header><h3>{label}</h3><p>{note}</p></header><ol>{ids.map((id, index) => {
    const item = documents.find((doc) => doc.id === id);
    return <li key={id}><button onClick={() => onSelect(id)} aria-pressed={id === selectedId}><span>{index + 1}</span><b>{id}</b><p>{item?.text.slice(0, 100)}…</p>{scores?.[id] != null && <code>{Math.abs(scores[id]) < 0.001 ? scores[id].toExponential(2) : scores[id].toFixed(4)}</code>}</button></li>;
  })}</ol></article>;
}

function RetrievalPanel({ candidates, selectedId, setSelectedId }) {
  const item = candidates.find((doc) => doc.id === selectedId) || candidates[0];
  return <><div className="rag-retrieval-grid"><RankedList label="Dense / LanceDB" note="Skor = 1 / (1 + mesafe) · büyük önce" ids={RETRIEVAL_DEMO.dense} documents={candidates} onSelect={setSelectedId} selectedId={item.id} scores={Object.fromEntries(RETRIEVAL_DEMO.documents.map((doc) => [doc.id, doc.denseScore]))} /><RankedList label="BM25 / SQLite FTS5" note="SQLite BM25 rank · küçük önce · C5 eşleşmedi" ids={RETRIEVAL_DEMO.bm25} documents={candidates} onSelect={setSelectedId} selectedId={item.id} scores={Object.fromEntries(RETRIEVAL_DEMO.documents.map((doc) => [doc.id, doc.bm25Score]))} /></div><div className="rag-selected-passage"><span className="rag-small-label">ADAYA TIKLA → İKİ LİSTEDEKİ YERİNİ VE METNİNİ GÖR</span><b>{item.id} · [{item.start}, {item.end})</b><p>{item.text}</p></div></>;
}

function FusionPanel({ rows, rerank, setRerank, selectedId, setSelectedId, finalRows }) {
  const focus = rows.find((row) => row.id === selectedId) || rows[0];
  const term = (rank) => rank ? `1 / (60 + ${rank}) = ${(1 / (60 + rank)).toFixed(6)}` : "Listede yok → 0";
  return <div className="rag-fusion-proof">
    <div className="rag-rrf-equation"><span>SEÇİLİ ADAY: <b>{focus.id}</b></span><div><article><small>DENSE KATKISI</small><code>{term(focus.denseRank)}</code></article><b>+</b><article><small>BM25 KATKISI</small><code>{term(focus.bm25Rank)}</code></article><b>=</b><strong>{focus.score.toFixed(6)}</strong></div><p>Ham BM25 ve dense skorları toplanmıyor. 60 sabiti ve 1’den başlayan sıra kullanılıyor.</p></div>
    <div className="rag-fusion-columns"><article><h3>RRF sırası</h3>{rows.map((row, index) => <button key={row.id} className="rag-rrf-row" aria-pressed={row.id === focus.id} onClick={() => setSelectedId(row.id)}><span>#{index + 1}</span><b>{row.id}</b><small>Dense {row.denseRank || "—"} · BM25 {row.bm25Rank || "—"}</small><code>{row.score.toFixed(6)}</code><i style={{ width: `${row.score / rows[0].score * 100}%` }} /></button>)}</article><article className="rag-rerank-box"><label><input type="checkbox" checked={rerank} onChange={(event) => setRerank(event.target.checked)} /><b>Opsiyonel reranker’ı göster</b></label><p>Cross-encoder, soru ve pasajı birlikte okuyup adayları yeniden sıralar.</p><div className="rag-rerank-order">{finalRows.map((row, index) => <span key={row.id}><small>#{index + 1}</small>{row.id}</span>)}</div><small>{rerank ? "Bu değişim temsili; burada cross-encoder çalıştırılmıyor. Üründe ayrıca yapılandırılır." : "Kapalı: RRF sırası korunur. Yeniden sıralama zorunlu bir adım değildir."}</small><div className="rag-decision-note">Karar: dev sorgularında kalite + gecikmeyi kıyasla. Hibrit veya reranker’ın daha iyi olduğu varsayılmaz.</div></article></div>
  </div>;
}

function ContextPanel({ contexts, topK, setTopK }) {
  return <div className="rag-context-panel"><div className="rag-context-controls"><label>LLM’e gönderilecek parça sayısı <select value={topK} onChange={(event) => setTopK(Number(event.target.value))}>{[1, 2, 3].map((value) => <option key={value} value={value}>top-{value}</option>)}</select></label><span>Demo kesimi; üründe varsayılan k=8</span></div><div className="rag-prompt-envelope"><header>LLM’E GİDEN PROMPT <span>{contexts.length} kaynak pasajı</span></header><div className="rag-system-instruction"><span>TALİMAT</span><p>Aşağıdaki kaynaklara dayanarak soruyu Türkçe, kaynak numaralarına atıf yaparak yanıtla. Bilgi yoksa bunu açıkça belirt, uydurma.</p></div><div className="rag-prompt-query"><span>SORU</span><p>{DEMO_QUERY}</p></div>{contexts.map((chunk, index) => <article key={chunk.id}><span className="rag-citation-badge">[{index + 1}]</span><div><b>{chunk.id} · {DEMO_SOURCE.title}</b><code>parent_id={DEMO_SOURCE.id} · token_start={chunk.start}</code><p>{chunk.text}</p></div></article>)}</div><div className="rag-experiment-note"><b>Bağlam daraltılır; bütün belge değil, seçilen kanıt gider.</b><span>Atıf numarası, bu prompt’taki sıradır. Kaynak kimliği kalıcıdır; sıra değişince [n] de değişir.</span></div></div>;
}

function AnswerPanel({ contexts, evidenceId, setEvidenceId, topK, setTopK, onSearch }) {
  const claims = ANSWER_DEMO.claims || [];
  const evidence = contexts.find((chunk) => chunk.id === evidenceId) || contexts[0];
  const quotation = claims.find((claim) => claim.sourceIDs.includes(evidence.id))?.quote;
  return <div className="rag-answer-panel"><div className="rag-context-controls"><label>Bağlamı daralt <select value={topK} onChange={(event) => setTopK(Number(event.target.value))}>{[1, 2, 3].map((value) => <option key={value} value={value}>top-{value}</option>)}</select></label><span>Kaynak çıkınca hangi iddia desteklenemiyor?</span></div><div className="rag-answer-grid"><article className="rag-answer-card"><span className="rag-small-label">ÖĞRETİM YANITI / LLM ÇAĞRISI YOK</span><h3>Fonlama oranı ne anlatıyor?</h3>{claims.map((claim, index) => {
    const ids = claim.sourceIDs || [];
    const supported = ids.length > 0 && ids.every((id) => contextCitation(id, contexts));
    return <div className={supported ? "rag-claim supported" : "rag-claim missing"} key={index}>{supported ? <><p>{claim.text} {ids.map((id) => <button key={id} aria-label={`${id} iddiasının kaynağını göster`} onClick={() => setEvidenceId(id)}>[{contextCitation(id, contexts)}]</button>)}</p><small><IconCheck width={13} height={13} />Kaynak bağlamda mevcut; desteği aşağıdaki pasajda incele.</small></> : <><p>{claim.text}</p><small>Bu iddianın {ids.join(" + ")} kaynağı seçili bağlamda yok → yanıt bunu kanıt olarak kullanmamalı.</small></>}</div>;
  })}<div className="rag-abstain"><b>Örnek: “Yarın kesin yükselir mi?”</b><p>Kaynaklar bunu doğrulamıyor. Doğru davranış: “Bu kanıtlardan kesin yön çıkarılamaz.”</p></div></article><article className="rag-evidence-card"><span className="rag-small-label">ATIF → KANIT</span><h3>[{contextCitation(evidence.id, contexts)}] {evidence.id}</h3>{quotation && evidence.text.includes(quotation) && <blockquote>{quotation}</blockquote>}<details><summary>Tüm kaynak pasajını incele</summary><p>{evidence.text}</p></details><code>{DEMO_SOURCE.id}#chunk-{String(Number(evidence.id.slice(1)) - 1).padStart(6, "0")}</code></article></div><div className="rag-experiment-note"><b>Prompt talimatı bir güvenlik garantisi değildir.</b><span>Üründe yanıt isteğe bağlı OpenRouter’dan gelir. Destek ve atıf kalitesi ayrıca insan etiketleriyle ölçülür.</span><button onClick={() => onSearch(DEMO_QUERY)}>Aynı soruyu gerçek arşivde aç <Arrow /></button></div></div>;
}

export default function RagWalkthrough({ reducedMotion, visible, onNavigate, onSearch }) {
  const [phase, setPhase] = useState(1);
  const [chunkSize, setChunkSize] = useState(240);
  const [overlap, setOverlap] = useState(40);
  const [selectedId, setSelectedId] = useState("C1");
  const [touring, setTouring] = useState(false);
  const [rerank, setRerank] = useState(false);
  const [topK, setTopK] = useState(3);
  const [evidenceId, setEvidenceId] = useState("C1");
  const chunks = useMemo(() => buildChunks(DEMO_SOURCE.tokens, chunkSize, overlap), [chunkSize, overlap]);
  const candidates = useMemo(() => buildChunks(DEMO_SOURCE.tokens, 240, 40).slice(0, 5).map((chunk) => ({ ...chunk, text: tokenRangeText(DEMO_SOURCE, chunk.start, chunk.end) })), []);
  const rows = useMemo(() => fusionRanking({ documents: candidates, dense: RETRIEVAL_DEMO.dense, bm25: RETRIEVAL_DEMO.bm25 }, "hybrid"), [candidates]);
  const finalRows = rerank ? RETRIEVAL_DEMO.reranked.map((id) => rows.find((row) => row.id === id)).filter(Boolean) : rows;
  const contexts = finalRows.slice(0, topK);
  const current = PHASES[phase];
  const selectedIndex = Math.max(0, chunks.findIndex((chunk) => chunk.id === selectedId));
  const stageChunks = phase < 2 ? chunks.slice(Math.max(0, selectedIndex - 2), Math.max(0, selectedIndex - 2) + 6) : candidates;
  const rankings = { dense: RETRIEVAL_DEMO.dense, bm25: RETRIEVAL_DEMO.bm25, fused: rows.map((row) => row.id), reranked: finalRows.map((row) => row.id), selected: contexts.map((row) => row.id) };
  const vectorsById = Object.fromEntries(RETRIEVAL_DEMO.documents.map((doc) => [doc.id, doc.vectorPreview]));
  const fusionScores = Object.fromEntries(rows.map((row) => [row.id, row.score]));
  const setSettings = (size, sharedTokens) => { setChunkSize(size); setOverlap(sharedTokens); setSelectedId("C1"); setTouring(false); };
  const go = (index) => { setPhase(index); setSelectedId("C1"); setTouring(false); };
  useEffect(() => {
    if (!touring || reducedMotion || !visible) return undefined;
    const timer = setTimeout(() => { if (phase === PHASES.length - 1) setTouring(false); else setPhase((value) => value + 1); }, 9000);
    return () => clearTimeout(timer);
  }, [touring, phase, reducedMotion, visible]);
  return <>
    <details className="rag-system-overview"><summary>Sistemin bütünü: rapor üretimi ve RAG iki ayrı hat <span>Şemayı aç ↓</span></summary><ArchitectureMap onNavigate={onNavigate} /></details>
    <section className="rag-walkthrough how-surface" aria-labelledby="rag-walkthrough-title" data-phase={phase}>
      <header className="rag-lab-heading"><div><span className="how-eyebrow">01 / BELGEDEN KANITA · ETKİLEŞİMLİ RAG</span><h2 id="rag-walkthrough-title">Bir sorunun bütün yolculuğu.</h2></div><div><span className="how-demo-tag">Öğretim veri seti</span><button disabled={reducedMotion} onClick={() => { if (touring) setTouring(false); else { setPhase(0); setTouring(true); } }}><IconPlay width={12} height={12} />{touring ? "Turu durdur" : "Akışı oynat"}</button></div></header>
      <p className="rag-demo-provenance">{DEMO_SOURCE.tokens.length} gerçek tokenizer tokenı · 240 / 40 ile 5 chunk · {RETRIEVAL_DEMO.vectorDimension} boyutlu gerçek embedding. Kurgu korpustaki dense / BM25 sonuçları önceden hesaplandı; tur canlı sorgu veya model çağrısı yapmaz.</p>
      <p className="rag-execution-timing"><b>01–03 · yeni belge:</b> chunk ve embedding kalıcı indekslere yazılır. <b>Her soruda:</b> yalnız soru vektörü üretilir, 04–07 çalışır.</p>
      <ol className="rag-phase-tabs" aria-label="RAG mekanizmasının adımları">{PHASES.map((item, index) => <li key={item.label}><button aria-pressed={phase === index} onClick={() => go(index)}><span>0{index + 1}</span><b>{item.label}</b></button></li>)}</ol>
      <div className="rag-phase-frame"><div className="rag-phase-explanation"><div><span className="rag-small-label">{String(phase + 1).padStart(2, "0")} / 07</span><h3>{current.title}</h3></div><div className="rag-input-output"><span>{current.input}</span><Arrow /><b>{current.output}</b></div><p>{current.why}</p></div>
        {phase !== 1 && <RagMechanismScene phase={phase} chunks={stageChunks} selectedChunkId={selectedId} onSelectChunk={setSelectedId} reducedMotion={reducedMotion} playing={!reducedMotion} rankings={rankings} vectorsById={vectorsById} fusionScores={fusionScores} sourceInfo={{ title: DEMO_SOURCE.title, tokenCount: DEMO_SOURCE.tokens.length, text: DEMO_SOURCE.text }} embeddingDimensions={RETRIEVAL_DEMO.vectorDimension} />}
        <div className="rag-phase-workspace" key={phase}>
          {phase === 0 && <SourcePanel />}
          {phase === 1 && <ChunkPanel chunkSize={chunkSize} overlap={overlap} setSettings={setSettings} chunks={chunks} selectedId={selectedId} setSelectedId={setSelectedId} />}
          {phase === 2 && <EmbeddingPanel candidates={candidates} selectedId={selectedId} setSelectedId={setSelectedId} />}
          {phase === 3 && <RetrievalPanel candidates={candidates} selectedId={selectedId} setSelectedId={setSelectedId} />}
          {phase === 4 && <FusionPanel rows={rows} finalRows={finalRows} rerank={rerank} setRerank={setRerank} selectedId={selectedId} setSelectedId={setSelectedId} />}
          {phase === 5 && <ContextPanel contexts={contexts} topK={topK} setTopK={setTopK} />}
          {phase === 6 && <AnswerPanel contexts={contexts} topK={topK} setTopK={setTopK} evidenceId={evidenceId} setEvidenceId={setEvidenceId} onSearch={onSearch} />}
        </div>
        {phase === 1 && <details className="rag-chunk-3d"><summary>Chunk’ların 3D dönüşümünü de göster ↓</summary><RagMechanismScene phase={phase} chunks={stageChunks} selectedChunkId={selectedId} onSelectChunk={setSelectedId} reducedMotion={reducedMotion} playing={!reducedMotion} rankings={rankings} vectorsById={vectorsById} fusionScores={fusionScores} sourceInfo={{ title: DEMO_SOURCE.title, tokenCount: DEMO_SOURCE.tokens.length, text: DEMO_SOURCE.text }} embeddingDimensions={RETRIEVAL_DEMO.vectorDimension} /></details>}
      </div>
      <footer className="rag-lab-footer"><a href="https://github.com/alikula37/crypto-deep-research/tree/main/src/crypto_deep_research/rag" target="_blank" rel="noreferrer">Kodda karşılığı: chunking.py · engine.py · store.py ↗</a><div><button disabled={phase === 0} onClick={() => go(phase - 1)}>← Önceki</button><button disabled={phase === 6} onClick={() => go(phase + 1)}>{phase === 1 ? "240 / 40 ile sorgu hattına geç" : "Sonraki adım"} <Arrow /></button></div></footer>
    </section>
  </>;
}
