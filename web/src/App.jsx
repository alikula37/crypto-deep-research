import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "./api.js";
import PriceChart from "./PriceChart.jsx";
import { DASH, formatDateTime, formatDuration, money, pct, price, priceRange, score } from "./format.js";

const TIMEFRAMES = ["15m", "30m", "1h", "4h", "1d", "1w"];
const TABS = [
  { id: "overview", label: "Genel Bakış" },
  { id: "findings", label: "Araştırma Bulguları" },
  { id: "report", label: "Rapor" },
  { id: "prompt", label: "Prompt Çıktısı" },
  { id: "rag", label: "Kaynak Arama" },
  { id: "history", label: "Rapor Arşivi" },
];

function scoreColor(value) {
  if (value === null || value === undefined) return "neutral";
  if (value > 0.15) return "positive";
  if (value < -0.15) return "negative";
  return "neutral";
}

function Badge({ status }) {
  const labels = { ok: "Tam", partial: "Kısmi", no_data: "Veri Yok", error: "Hata" };
  return <span className={`badge badge-${status}`}>{labels[status] || status}</span>;
}

function ScorePill({ value }) {
  if (value === null || value === undefined) return <span className="score neutral">—</span>;
  return <span className={`score ${scoreColor(value)}`}>{score(value)}</span>;
}

function ProbabilityBar({ up, down }) {
  if (up === null || up === undefined) return null;
  const upValue = Math.max(0, Math.min(100, Number(up)));
  const downValue = Math.max(0, Math.min(100, Number(down ?? 100 - upValue)));
  return (
    <div className="prob">
      <div className="prob-labels">
        <span className="up">Yükseliş %{upValue.toFixed(1)}</span>
        <span className="down">Düşüş %{downValue.toFixed(1)}</span>
      </div>
      <div className="prob-bar">
        <div className="prob-up" style={{ width: `${upValue}%` }} />
        <div className="prob-down" style={{ width: `${downValue}%` }} />
      </div>
    </div>
  );
}

function SnapshotCard({ data }) {
  if (!data) return null;
  const s = data.snapshot;
  const g = data.global;
  const stats = [
    ["Fiyat", price(s.price_usd)],
    ["Piyasa değeri", money(s.market_cap_usd)],
    ["Sıra", s.rank ? `#${s.rank}` : DASH],
    ["24s hacim", money(s.volume_24h_usd)],
    ["24s", pct(s.change_24h_pct, { signed: true })],
    ["7g", pct(s.change_7d_pct, { signed: true })],
    ["30g", pct(s.change_30d_pct, { signed: true })],
    ["ATH uzaklığı", pct(s.ath_change_pct)],
    ["ATL uzaklığı", pct(s.atl_change_pct)],
    ["BTC dominansı", g?.btc_dominance != null ? `%${g.btc_dominance.toFixed(1)}` : DASH],
    ["ETH dominansı", g?.eth_dominance != null ? `%${g.eth_dominance.toFixed(1)}` : DASH],
    ["Toplam piyasa değeri", money(g?.total_market_cap_usd)],
  ];
  return (
    <div
      className="snapshot-grid"
      title={`Tam değerler: fiyat ${s.price_usd} USD · piyasa değeri ${s.market_cap_usd} USD`}
    >
      {stats.map(([label, value]) => (
        <div className="stat" key={label}>
          <span className="stat-label">{label}</span>
          <span className="stat-value">{value}</span>
        </div>
      ))}
    </div>
  );
}

function ScoreDistribution({ items }) {
  const counts = { positive: 0, negative: 0, neutral: 0 };
  for (const item of items) {
    if (item.score === null || item.score === undefined || !item.confidence) continue;
    if (item.score > 0.15) counts.positive += 1;
    else if (item.score < -0.15) counts.negative += 1;
    else counts.neutral += 1;
  }
  const total = counts.positive + counts.negative + counts.neutral;
  if (!total) return null;
  return (
    <div className="distribution">
      <span className="chip positive-chip">Pozitif {counts.positive}</span>
      <span className="chip neutral-chip">Nötr {counts.neutral}</span>
      <span className="chip negative-chip">Negatif {counts.negative}</span>
    </div>
  );
}

function AnalysisCard({ result }) {
  const reasons = result.data?.reasons || [];
  return (
    <div className={`card analysis-card ${scoreColor(result.score)}`}>
      <div className="card-head">
        <h3>{result.title}</h3>
        <div className="card-meta">
          <Badge status={result.status} />
          <ScorePill value={result.score} />
          <span className="confidence">Güven {(result.confidence ?? 0).toFixed(2)}</span>
        </div>
      </div>
      <p className="summary">{result.summary}</p>
      {reasons.length > 0 && (
        <ul className="reasons">
          {reasons.slice(0, 6).map((reason, index) => (
            <li key={index}>{reason}</li>
          ))}
        </ul>
      )}
      {result.sources?.length > 0 && (
        <div className="sources">
          {[...new Set(result.sources.map((s) => s.name))].map((name) => (
            <span className="source-chip" key={name}>{name}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function FindingsTable({ items }) {
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("order");

  const filtered = useMemo(() => {
    let list = items;
    if (filter === "scored") list = list.filter((item) => item.score !== null && item.confidence > 0);
    else if (filter !== "all") list = list.filter((item) => item.status === filter);
    if (query.trim()) {
      const needle = query.trim().toLowerCase();
      list = list.filter(
        (item) =>
          item.title_tr.toLowerCase().includes(needle) ||
          (item.summary || "").toLowerCase().includes(needle)
      );
    }
    if (sort === "score-desc") list = [...list].sort((a, b) => (b.score ?? -99) - (a.score ?? -99));
    else if (sort === "score-asc") list = [...list].sort((a, b) => (a.score ?? 99) - (b.score ?? 99));
    else if (sort === "confidence") list = [...list].sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0));
    return list;
  }, [items, filter, query, sort]);

  return (
    <div>
      <div className="filter-row">
        {[
          ["all", "Tümü"],
          ["scored", "Skorlanan"],
          ["ok", "Tam"],
          ["partial", "Kısmi"],
          ["no_data", "Veri Yok"],
        ].map(([id, label]) => (
          <button
            key={id}
            className={`chip ${filter === id ? "active" : ""}`}
            onClick={() => setFilter(id)}
          >
            {label}
          </button>
        ))}
        <input
          className="search-input"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Kriter ara…"
        />
        <select value={sort} onChange={(event) => setSort(event.target.value)} className="sort-select">
          <option value="order">Numara</option>
          <option value="score-desc">Skor (azalan)</option>
          <option value="score-asc">Skor (artan)</option>
          <option value="confidence">Güven</option>
        </select>
        <span className="muted">{filtered.length} kriter</span>
      </div>
      <div className="items-grid">
        {filtered.map((item) => (
          <div className="card item-card" key={item.item_id}>
            <div className="card-head">
              <h4>
                <span className="item-no">{item.item_id}</span> {item.title_tr}
              </h4>
              <div className="card-meta">
                <Badge status={item.status} />
                <ScorePill value={item.score} />
              </div>
            </div>
            <p className="summary clamp-3">{item.summary}</p>
            <div className="item-footer">
              <span className="muted">
                {item.category} · Ağırlık {item.weight} · Güven {(item.confidence ?? 0).toFixed(2)}
              </span>
              {item.sources?.length > 0 && (
                <span className="muted">
                  {[...new Set(item.sources.map((s) => s.name))].slice(0, 3).join(", ")}
                </span>
              )}
            </div>
            {item.data && Object.keys(item.data).length > 0 && (
              <details className="item-data">
                <summary>Teknik veriyi göster</summary>
                <pre>{JSON.stringify(item.data, null, 2)}</pre>
              </details>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function Markdown({ children }) {
  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children || ""}</ReactMarkdown>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="grid">
      {[0, 1, 2, 3].map((key) => (
        <div className="card skeleton-card" key={key}>
          <div className="skeleton-line short" />
          <div className="skeleton-line" />
          <div className="skeleton-line" />
        </div>
      ))}
    </div>
  );
}

function JobProgress({ job, elapsed }) {
  const progress = Math.max(0, Math.min(100, job?.progress ?? 0));
  return (
    <div className="job-progress">
      <div className="job-head">
        <span>{job?.message || "Görev başlatılıyor…"}</span>
        <span className="muted">Süre {formatDuration(elapsed)}</span>
      </div>
      <div className="job-bar">
        <div className="job-fill" style={{ width: `${progress}%` }} />
      </div>
      <span className="muted small">
        Derin araştırma birkaç dakika sürebilir; sayfayı kapatmadan bekleyin. İlerleme otomatik güncellenir.
      </span>
    </div>
  );
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [analysesList, setAnalysesList] = useState([]);
  const [items, setItems] = useState([]);
  const [coin, setCoin] = useState("bitcoin");
  const [timeframe, setTimeframe] = useState("1d");
  const [lookback, setLookback] = useState(365);
  const [selected, setSelected] = useState([]);
  const [platform, setPlatform] = useState("generic");
  const [tab, setTab] = useState("overview");
  const [snapshotData, setSnapshotData] = useState(null);
  const [analysisResults, setAnalysisResults] = useState([]);
  const [deep, setDeep] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [job, setJob] = useState(null);
  const [jobStartedAt, setJobStartedAt] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [ragQuery, setRagQuery] = useState("");
  const [ragResults, setRagResults] = useState([]);
  const [ragAnswer, setRagAnswer] = useState(null);
  const [reports, setReports] = useState([]);
  const [ragStats, setRagStats] = useState(null);
  const [selectedReport, setSelectedReport] = useState(null);
  const [copied, setCopied] = useState("");

  useEffect(() => {
    api.health().then(setHealth).catch(() => {});
    api.analyses().then(setAnalysesList).catch(() => {});
    api.items().then(setItems).catch(() => {});
    api.reports().then(setReports).catch(() => {});
    api.ragStats().then(setRagStats).catch(() => {});
  }, []);

  useEffect(() => {
    if (busy !== "deep" || !jobStartedAt) return undefined;
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - jobStartedAt) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [busy, jobStartedAt]);

  const toggleAnalysis = (key) => {
    setSelected((prev) => (prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key]));
  };

  const loadSnapshot = async () => {
    setBusy("snapshot");
    setError("");
    try {
      setSnapshotData(await api.snapshot(coin));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  };

  const runAnalyze = async () => {
    setBusy("analyze");
    setError("");
    try {
      const payload = {
        coin,
        timeframe,
        lookback_days: Number(lookback),
        analyses: selected.length ? selected : null,
      };
      const [snapshot, analysis] = await Promise.all([api.snapshot(coin), api.analyze(payload)]);
      setSnapshotData(snapshot);
      setAnalysisResults(analysis.analyses);
      setDeep(null);
      setTab("overview");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  };

  const runDeepResearch = async () => {
    setBusy("deep");
    setError("");
    setDeep(null);
    setAnalysisResults([]);
    setElapsed(0);
    setJobStartedAt(Date.now());
    try {
      await api.health();
      const payload = {
        coin,
        timeframe,
        lookback_days: Number(lookback),
        platform,
        analyses: selected.length ? selected : null,
        include_prompt: true,
      };
      let state = await api.startDeepResearch(payload);
      setJob(state);
      while (state.status === "queued" || state.status === "running") {
        await new Promise((resolve) => setTimeout(resolve, 2500));
        state = await api.jobStatus(state.job_id);
        setJob(state);
      }
      if (state.status === "error") {
        throw new Error(state.error || "Araştırma tamamlanamadı.");
      }
      const result = state.result;
      setDeep(result);
      setAnalysisResults(result.analyses || []);
      setSnapshotData(await api.snapshot(coin));
      setTab("report");
      api.reports().then(setReports).catch(() => {});
      api.ragStats().then(setRagStats).catch(() => {});
    } catch (err) {
      setError(err.message);
    } finally {
      setJob(null);
      setBusy("");
    }
  };

  const runRagSearch = async (mode) => {
    if (!ragQuery.trim()) return;
    setBusy(mode);
    setError("");
    try {
      if (mode === "rag-ask") {
        setRagAnswer(await api.ragAsk({ query: ragQuery, coin, k: 8 }));
      } else {
        setRagResults((await api.ragSearch({ query: ragQuery, coin, k: 10 })).results);
        setRagAnswer(null);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  };

  const downloadReport = () => {
    if (!deep?.markdown) return;
    const blob = new Blob([deep.markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${deep.run.coin.symbol.toUpperCase()}_rapor.md`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const copyReport = async () => {
    if (!deep?.markdown) return;
    await navigator.clipboard.writeText(deep.markdown);
    setCopied("report");
    setTimeout(() => setCopied(""), 2000);
  };

  const downloadPrompt = () => {
    if (!deep?.prompt) return;
    const blob = new Blob([deep.prompt], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${deep.run.coin.symbol.toUpperCase()}_prompt.txt`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const copyPrompt = async () => {
    if (!deep?.prompt) return;
    await navigator.clipboard.writeText(deep.prompt);
    setCopied("prompt");
    setTimeout(() => setCopied(""), 2000);
  };

  const run = deep?.run;
  const scoredItems = items.filter((item) => item.score !== null && item.confidence > 0);

  return (
    <div className="app">
      <aside className="sidebar">
        <h1>
          Crypto<span>DeepResearch</span>
        </h1>
        <p className="muted small">
          Kripto varlıklar için yerel RAG ve derin araştırma altyapısı
        </p>

        <label className="field">
          <span>Varlık (sembol veya CoinGecko kimliği)</span>
          <input
            value={coin}
            onChange={(event) => setCoin(event.target.value)}
            onBlur={loadSnapshot}
            placeholder="örn. bitcoin, eth, chainlink"
          />
        </label>

        <div className="field-row">
          <label className="field">
            <span>Zaman Dilimi</span>
            <select value={timeframe} onChange={(event) => setTimeframe(event.target.value)}>
              {TIMEFRAMES.map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Geriye Dönük Veri (gün)</span>
            <input
              type="number"
              min="30"
              max="3650"
              value={lookback}
              onChange={(event) => setLookback(event.target.value)}
            />
          </label>
        </div>

        <div className="field">
          <span>Analiz Modülleri {selected.length ? `(${selected.length} seçili)` : "(tümü)"}</span>
          <div className="checklist">
            {analysesList.map((analysis) => (
              <label key={analysis.key} className="check">
                <input
                  type="checkbox"
                  checked={selected.includes(analysis.key)}
                  onChange={() => toggleAnalysis(analysis.key)}
                />
                <span>{analysis.title}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="field-row">
          <label className="field">
            <span>Prompt Hedefi</span>
            <select value={platform} onChange={(event) => setPlatform(event.target.value)}>
              <option value="generic">Genel</option>
              <option value="claude">Claude</option>
              <option value="codex">Codex</option>
              <option value="chatgpt">ChatGPT</option>
            </select>
          </label>
        </div>

        <button className="primary" onClick={runAnalyze} disabled={!!busy}>
          {busy === "analyze" ? "Analiz çalışıyor…" : "Analiz Çalıştır"}
        </button>
        <button className="accent" onClick={runDeepResearch} disabled={!!busy}>
          {busy === "deep" ? "Derin araştırma sürüyor…" : "Derin Araştırma Başlat"}
        </button>

        {snapshotData && (
          <div className="sidebar-price">
            {snapshotData.snapshot.coin.symbol.toUpperCase()} {price(snapshotData.snapshot.price_usd)}
          </div>
        )}

        <div className="sidebar-footer">
          {health && (
            <>
              <div className="muted small">
                API anahtarları: {Object.entries(health.keys).filter(([, value]) => value).map(([key]) => key).join(", ") || "tanımlı değil"}
              </div>
              <div className="muted small">
                OpenRouter: {health.openrouter ? "aktif" : "pasif (yalnızca prompt üretilir)"}
              </div>
              <div className="muted small">
                Rapor: {health.reports} · Vektör kaydı: {ragStats?.vectors ?? 0}
              </div>
            </>
          )}
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <nav className="tabs">
            {TABS.map((item) => (
              <button
                key={item.id}
                className={tab === item.id ? "active" : ""}
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </nav>
          {run && (
            <div className="score-summary">
              <span className={scoreColor(run.weighted_score)}>Skor {score(run.weighted_score)}</span>
              <span className="up">Yükseliş %{Number(run.up_probability).toFixed(1)}</span>
              <span className="down">Düşüş %{Number(run.down_probability).toFixed(1)}</span>
              <span className="range">{priceRange(run.expected_low, run.expected_high)}</span>
            </div>
          )}
        </header>

        {error && <div className="error">{error}</div>}
        {busy === "deep" && <JobProgress job={job} elapsed={elapsed} />}
        {busy === "analyze" && <div className="progress">Analiz çalışıyor…</div>}

        <section className="content">
          {tab === "overview" && (
            <>
              <SnapshotCard data={snapshotData} />
              {(snapshotData || analysisResults.length > 0) && (
                <PriceChart coin={coin} defaultTimeframe={timeframe} />
              )}
              {run && (
                <div className="card">
                  <h3>Olasılık Dağılımı</h3>
                  <ProbabilityBar up={run.up_probability} down={run.down_probability} />
                  <div className="range-line">
                    Beklenen fiyat aralığı: <b>{priceRange(run.expected_low, run.expected_high)}</b>
                  </div>
                  <ScoreDistribution items={run.items} />
                </div>
              )}
              {!snapshotData && !busy && (
                <div className="empty">
                  Başlamak için sol panelden bir varlık seçin ve <b>Analiz Çalıştır</b> veya{" "}
                  <b>Derin Araştırma Başlat</b> düğmesine basın.
                </div>
              )}
              {(busy === "analyze" || busy === "deep") && analysisResults.length === 0 && <Skeleton />}
              <div className="grid">
                {analysisResults.map((result) => (
                  <AnalysisCard key={result.key || result.title} result={result} />
                ))}
              </div>
            </>
          )}

          {tab === "findings" && (
            <>
              {!run && scoredItems.length === 0 && (
                <div className="empty">
                  Araştırma bulgularını görmek için <b>Derin Araştırma Başlat</b> düğmesini kullanın.
                  Böylece 66 kriterin tamamı veri, kaynak ve skorla doldurulur.
                </div>
              )}
              {run && <FindingsTable items={run.items} />}
              {!run && scoredItems.length > 0 && <FindingsTable items={items} />}
            </>
          )}

          {tab === "report" && (
            <>
              {!deep && (
                <div className="empty">Rapor üretmek için derin araştırma başlatın.</div>
              )}
              {deep && (
                <>
                  <div className="toolbar">
                    <button onClick={copyReport}>{copied === "report" ? "Kopyalandı ✓" : "Kopyala"}</button>
                    <button onClick={downloadReport}>Markdown İndir</button>
                    <button onClick={() => window.print()}>Yazdır / PDF</button>
                    <span className="muted">
                      {deep.report_path} · Bağlam: {JSON.stringify(deep.context_stats?.groups || {})}
                    </span>
                  </div>
                  <Markdown>{deep.markdown}</Markdown>
                </>
              )}
            </>
          )}

          {tab === "prompt" && (
            <>
              {!deep && <div className="empty">Prompt üretmek için derin araştırma başlatın.</div>}
              {deep && (
                <>
                  <div className="toolbar">
                    <button onClick={copyPrompt}>{copied === "prompt" ? "Kopyalandı ✓" : "Kopyala"}</button>
                    <button onClick={downloadPrompt}>İndir</button>
                    <span className="muted">
                      Bu metni Claude, ChatGPT, Codex veya OpenRouter gibi araçlara yapıştırabilirsiniz
                      · {deep.prompt?.length ?? 0} karakter
                    </span>
                  </div>
                  <textarea className="prompt-box" readOnly value={deep.prompt || ""} />
                </>
              )}
            </>
          )}

          {tab === "rag" && (
            <>
              <div className="toolbar">
                <input
                  value={ragQuery}
                  onChange={(event) => setRagQuery(event.target.value)}
                  placeholder="Araştırma notlarında ve haberlerde ara…"
                  onKeyDown={(event) => event.key === "Enter" && runRagSearch("rag-search")}
                />
                <button onClick={() => runRagSearch("rag-search")} disabled={!!busy}>
                  Ara
                </button>
                <button onClick={() => runRagSearch("rag-ask")} disabled={!!busy}>
                  {health?.openrouter ? "AI ile Yanıtla" : "RAG Prompt Oluştur"}
                </button>
              </div>
              {ragAnswer && (
                <div className="card">
                  {ragAnswer.answer ? (
                    <Markdown>{ragAnswer.answer}</Markdown>
                  ) : (
                    <>
                      <p className="muted">{ragAnswer.note}</p>
                      <textarea className="prompt-box" readOnly value={ragAnswer.prompt} />
                    </>
                  )}
                </div>
              )}
              <div className="grid">
                {ragResults.map((result, index) => (
                  <div className="card" key={`${result.key}-${index}`}>
                    <div className="card-head">
                      <h4>{result.source || "kaynak"}</h4>
                      <span className="muted">{result.score?.toFixed(3)}</span>
                    </div>
                    <p className="summary break-anywhere">{result.content}</p>
                  </div>
                ))}
              </div>
            </>
          )}

          {tab === "history" && (
            <>
              <div className="toolbar">
                <span className="muted">{reports.length} rapor</span>
                <button onClick={() => api.reports().then(setReports)}>Yenile</button>
              </div>
              <div className="reports-list">
                {reports.map((report) => (
                  <button
                    key={report.name}
                    className="report-row"
                    onClick={async () => setSelectedReport(await api.report(report.name))}
                  >
                    <b>{report.coin}</b>
                    <span className="break-anywhere">{report.name}</span>
                    <span className="muted">
                      {formatDateTime(report.created_at ? report.created_at * 1000 : null)}
                    </span>
                  </button>
                ))}
              </div>
              {selectedReport && (
                <>
                  <div className="toolbar">
                    <b className="break-anywhere">{selectedReport.name}</b>
                    <button onClick={() => window.print()}>Yazdır / PDF</button>
                    <button onClick={() => setSelectedReport(null)}>Kapat</button>
                  </div>
                  <Markdown>{selectedReport.markdown}</Markdown>
                </>
              )}
            </>
          )}
        </section>
      </main>
    </div>
  );
}
