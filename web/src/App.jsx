import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "./api.js";

const TIMEFRAMES = ["15m", "30m", "1h", "4h", "1d", "1w"];
const TABS = [
  { id: "overview", label: "Analizler" },
  { id: "items", label: "66 Madde" },
  { id: "report", label: "Rapor" },
  { id: "prompt", label: "Prompt" },
  { id: "rag", label: "RAG Arama" },
  { id: "history", label: "Gecmis" },
];

function scoreColor(score) {
  if (score === null || score === undefined) return "neutral";
  if (score > 0.15) return "positive";
  if (score < -0.15) return "negative";
  return "neutral";
}

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return Number(value).toLocaleString("tr-TR", { maximumFractionDigits: digits });
}

function Badge({ status }) {
  const labels = { ok: "Tam", partial: "Kismi", no_data: "Veri yok", error: "Hata" };
  return <span className={`badge badge-${status}`}>{labels[status] || status}</span>;
}

function ScorePill({ score }) {
  if (score === null || score === undefined) return <span className="score neutral">-</span>;
  return <span className={`score ${scoreColor(score)}`}>{score >= 0 ? "+" : ""}{score.toFixed(3)}</span>;
}

function SnapshotCard({ data }) {
  if (!data) return null;
  const s = data.snapshot;
  const g = data.global;
  const items = [
    ["Fiyat", `$${formatNumber(s.price_usd, s.price_usd < 1 ? 6 : 2)}`],
    ["Piyasa degeri", `$${formatNumber(s.market_cap_usd, 0)}`],
    ["Sira", `#${s.rank ?? "-"}`],
    ["24s hacim", `$${formatNumber(s.volume_24h_usd, 0)}`],
    ["24s", `${formatNumber(s.change_24h_pct)}%`],
    ["7g", `${formatNumber(s.change_7d_pct)}%`],
    ["30g", `${formatNumber(s.change_30d_pct)}%`],
    ["ATH uzaklik", `${formatNumber(s.ath_change_pct)}%`],
    ["ATL uzaklik", `${formatNumber(s.atl_change_pct)}%`],
    ["BTC dominance", `${formatNumber(g?.btc_dominance)}%`],
    ["ETH dominance", `${formatNumber(g?.eth_dominance)}%`],
    ["Toplam mcap", `$${formatNumber(g?.total_market_cap_usd, 0)}`],
  ];
  return (
    <div className="snapshot-grid">
      {items.map(([label, value]) => (
        <div className="stat" key={label}>
          <span className="stat-label">{label}</span>
          <span className="stat-value">{value}</span>
        </div>
      ))}
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
          <ScorePill score={result.score} />
          <span className="confidence">guven {result.confidence.toFixed(2)}</span>
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

function ItemsTable({ items }) {
  const [filter, setFilter] = useState("all");
  const filtered = useMemo(() => {
    if (filter === "all") return items;
    if (filter === "scored") return items.filter((i) => i.score !== null && i.confidence > 0);
    return items.filter((i) => i.status === filter);
  }, [items, filter]);
  return (
    <div>
      <div className="filter-row">
        {[
          ["all", "Tumu"],
          ["scored", "Skorlananlar"],
          ["ok", "Tam"],
          ["partial", "Kismi"],
          ["no_data", "Veri yok"],
        ].map(([id, label]) => (
          <button
            key={id}
            className={`chip ${filter === id ? "active" : ""}`}
            onClick={() => setFilter(id)}
          >
            {label}
          </button>
        ))}
        <span className="muted">{filtered.length} madde</span>
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
                <ScorePill score={item.score} />
              </div>
            </div>
            <p className="summary">{item.summary}</p>
            <div className="item-footer">
              <span className="muted">
                {item.category} | agirlik {item.weight} | guven {item.confidence.toFixed(2)}
              </span>
              {item.sources?.length > 0 && (
                <span className="muted">
                  {[...new Set(item.sources.map((s) => s.name))].slice(0, 3).join(", ")}
                </span>
              )}
            </div>
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
  const [ragQuery, setRagQuery] = useState("");
  const [ragResults, setRagResults] = useState([]);
  const [ragAnswer, setRagAnswer] = useState(null);
  const [reports, setReports] = useState([]);
  const [ragStats, setRagStats] = useState(null);
  const [selectedReport, setSelectedReport] = useState(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => {});
    api.analyses().then(setAnalysesList).catch(() => {});
    api.items().then(setItems).catch(() => {});
    api.reports().then(setReports).catch(() => {});
    api.ragStats().then(setRagStats).catch(() => {});
  }, []);

  const toggleAnalysis = (key) => {
    setSelected((prev) =>
      prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key]
    );
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
      const [snapshot, analysis] = await Promise.all([
        api.snapshot(coin),
        api.analyze(payload),
      ]);
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
    try {
      const payload = {
        coin,
        timeframe,
        lookback_days: Number(lookback),
        platform,
        analyses: selected.length ? selected : null,
        include_prompt: true,
      };
      const result = await api.deepResearch(payload);
      setDeep(result);
      setAnalysisResults(result.analyses || []);
      setSnapshotData(await api.snapshot(coin));
      setTab("report");
      api.reports().then(setReports).catch(() => {});
      api.ragStats().then(setRagStats).catch(() => {});
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  };

  const runRagSearch = async (mode) => {
    if (!ragQuery.trim()) return;
    setBusy(mode);
    setError("");
    try {
      if (mode === "rag-ask") {
        const result = await api.ragAsk({ query: ragQuery, coin, k: 8 });
        setRagAnswer(result);
      } else {
        const result = await api.ragSearch({ query: ragQuery, coin, k: 10 });
        setRagResults(result.results);
        setRagAnswer(null);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
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
          Yerel RAG + 66 maddelik arastirma. Veriler ucretsiz kaynaklardan toplanir.
        </p>

        <label className="field">
          <span>Coin (sembol veya id)</span>
          <input
            value={coin}
            onChange={(event) => setCoin(event.target.value)}
            onBlur={loadSnapshot}
            placeholder="bitcoin, eth, sol..."
          />
        </label>

        <div className="field-row">
          <label className="field">
            <span>Timeframe</span>
            <select value={timeframe} onChange={(event) => setTimeframe(event.target.value)}>
              {TIMEFRAMES.map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Gecmis (gun)</span>
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
          <span>Analizler {selected.length ? `(${selected.length} secili)` : "(tumu)"}</span>
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
            <span>Platform</span>
            <select value={platform} onChange={(event) => setPlatform(event.target.value)}>
              <option value="generic">generic</option>
              <option value="claude">claude</option>
              <option value="codex">codex</option>
              <option value="chatgpt">chatgpt</option>
            </select>
          </label>
        </div>

        <button className="primary" onClick={runAnalyze} disabled={!!busy}>
          {busy === "analyze" ? "Analiz ediliyor..." : "Analiz Et"}
        </button>
        <button className="accent" onClick={runDeepResearch} disabled={!!busy}>
          {busy === "deep" ? "Arastirma suruyor (dakikalar)..." : "Deep Research + Prompt"}
        </button>

        {snapshotData && (
          <div className="sidebar-price">
            {snapshotData.snapshot.coin.symbol.toUpperCase()} ${formatNumber(snapshotData.snapshot.price_usd, 4)}
          </div>
        )}

        <div className="sidebar-footer">
          {health && (
            <>
              <div className="muted small">
                Anahtarlar: {Object.entries(health.keys).filter(([, v]) => v).map(([k]) => k).join(", ") || "yok"}
              </div>
              <div className="muted small">
                OpenRouter: {health.openrouter ? "aktif" : "yok (prompt uretilir)"}
              </div>
              <div className="muted small">
                Rapor: {health.reports} | Vektor: {ragStats?.vectors ?? 0}
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
              <span className={scoreColor(run.weighted_score)}>
                skor {run.weighted_score ?? "-"}
              </span>
              <span className="up">yukselis %{run.up_probability}</span>
              <span className="down">dusus %{run.down_probability}</span>
              <span className="range">
                {formatNumber(run.expected_low, 4)} - {formatNumber(run.expected_high, 4)}
              </span>
            </div>
          )}
        </header>

        {error && <div className="error">{error}</div>}
        {busy && <div className="progress">{busy === "deep" ? "Deep research calisiyor; 66 madde ve tum analizler toplaniyor..." : "Calisiyor..."}</div>}

        <section className="content">
          {tab === "overview" && (
            <>
              <SnapshotCard data={snapshotData} />
              {!snapshotData && !busy && (
                <div className="empty">
                  Soldan bir coin secip <b>Analiz Et</b> veya <b>Deep Research</b> baslatin.
                </div>
              )}
              <div className="grid">
                {analysisResults.map((result) => (
                  <AnalysisCard key={result.key || result.title} result={result} />
                ))}
              </div>
            </>
          )}

          {tab === "items" && (
            <>
              {scoredItems.length === 0 && (
                <div className="empty">
                  66 maddenin tamami icin once <b>Deep Research</b> calistirin. Boylece her madde
                  veri, kaynak ve skorla doldurulur.
                </div>
              )}
              {run && <ItemsTable items={run.items} />}
              {!run && scoredItems.length > 0 && <ItemsTable items={items} />}
            </>
          )}

          {tab === "report" && (
            <>
              {!deep && <div className="empty">Rapor icin Deep Research calistirin.</div>}
              {deep && (
                <>
                  <div className="toolbar">
                    <span className="muted">
                      {deep.report_path} | Context: {JSON.stringify(deep.context_stats?.groups || {})}
                    </span>
                  </div>
                  <Markdown>{deep.markdown}</Markdown>
                </>
              )}
            </>
          )}

          {tab === "prompt" && (
            <>
              {!deep && <div className="empty">Prompt icin Deep Research calistirin.</div>}
              {deep && (
                <>
                  <div className="toolbar">
                    <button onClick={copyPrompt}>Panoya kopyala</button>
                    <button onClick={downloadPrompt}>Indir</button>
                    <span className="muted">{deep.prompt?.length ?? 0} karakter</span>
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
                  placeholder="Ornek: ETF akislari, likidasyon, regülasyon..."
                  onKeyDown={(event) => event.key === "Enter" && runRagSearch("rag-search")}
                />
                <button onClick={() => runRagSearch("rag-search")} disabled={!!busy}>
                  Ara
                </button>
                <button onClick={() => runRagSearch("rag-ask")} disabled={!!busy}>
                  {health?.openrouter ? "AI ile Yanitla" : "RAG Prompt Olustur"}
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
                    <p className="summary">{result.content}</p>
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
                    <span>{report.name}</span>
                    <span className="muted">
                      {new Date(report.created_at * 1000).toLocaleString("tr-TR")}
                    </span>
                  </button>
                ))}
              </div>
              {selectedReport && (
                <>
                  <div className="toolbar">
                    <b>{selectedReport.name}</b>
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
