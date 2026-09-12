import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "./api.js";
import CoinSelect from "./CoinSelect.jsx";
import PriceChart from "./PriceChart.jsx";
import ScoreHistoryChart from "./ScoreHistoryChart.jsx";
import AccuracyPanel from "./AccuracyPanel.jsx";
import {
  IconAlert,
  IconCheck,
  IconChart,
  IconCoins,
  IconCopy,
  IconDoc,
  IconDownload,
  IconHistory,
  IconInfo,
  IconPlay,
  IconPrinter,
  IconRefresh,
  IconSearch,
  IconSparkles,
  IconTarget,
  IconWand,
  IconX,
} from "./icons.jsx";
import { DASH, formatDateTime, formatDuration, money, pct, price, priceRange, score } from "./format.js";

const TIMEFRAMES = ["15m", "30m", "1h", "4h", "1d", "1w"];
const TABS = [
  { id: "overview", label: "Genel Bakış", icon: IconChart },
  { id: "findings", label: "Araştırma Bulguları", icon: IconSparkles },
  { id: "accuracy", label: "İsabet", icon: IconTarget },
  { id: "report", label: "Rapor", icon: IconDoc },
  { id: "prompt", label: "Prompt Çıktısı", icon: IconWand },
  { id: "rag", label: "Kaynak Arama", icon: IconSearch },
  { id: "history", label: "Rapor Arşivi", icon: IconHistory },
];

const STATUS_META = {
  ok: { label: "Tam", tone: "ok", icon: IconCheck },
  partial: { label: "Kısmi", tone: "warn", icon: IconAlert },
  no_data: { label: "Veri Yok", tone: "muted", icon: IconX },
  error: { label: "Hata", tone: "error", icon: IconX },
  pending: { label: "Sırada…", tone: "pending", icon: IconRefresh },
  not_run: { label: "Çalıştırılmadı", tone: "idle", icon: IconPlay },
  idle: { label: "Seçilmedi", tone: "idle", icon: IconPlay },
};

const TAB_INTROS = {
  overview: {
    title: "Genel Bakış",
    summary: "Varlığın anlık piyasa görüntüsü, fiyat grafiği, modül durumları ve ağırlıklı skor özeti.",
    points: [
      "Üstteki kartlar fiyat, piyasa değeri, hacim ve ATH/ATL uzaklığı gibi anlık verileri gösterir.",
      "Olasılık dağılımı 66 kriterin ağırlıklı skorundan türetilir ve ±%45 sınırıyla gösterilir.",
      "Beklenen fiyat aralığı, ATR bazlı oynaklık ve skor yönü kullanılarak hesaplanır.",
      "Analiz Modülleri panelinde her modülün Tam/Kısmi/Veri yok durumu görünür; sonuca tıklayınca kartına gidilir.",
    ],
  },
  findings: {
    title: "Araştırma Bulguları",
    summary: "66 kriterin her biri için neyin araştırıldığı, bulgu, skor ve güven bilgisi.",
    points: [
      "Her karttaki 'Ne araştırılır?' satırı, o kriterin baktığı veriyi ve yöntemi anlatır.",
      "Durum: Tam (yeterli veri), Kısmi (sınırlı veri), Veri Yok (doğrulanabilir ücretsiz kaynak bulunamadı).",
      "Skor −1 ile +1 arasındadır: eksi baskı/düşüş, artı destek/yükseliş yönündedir.",
      "Güven 0–1 arasındadır; düşük güvenli skorlar ağırlıklı ortalamada daha az etkili olur.",
      "Ağırlık, kriterin genel skora katkı katsayısıdır; yüksek ağırlık daha belirleyici demektir.",
      "Aynı analiz modülünü paylaşan kriterler tek sinyal sayılır; kısmi veri yarım ağırlıkla katkı verir.",
      "Derin araştırma çalıştırılmadan önce bu sekmede 66 kriterin tümü açıklamalarıyla listelenir.",
    ],
  },
  accuracy: {
    title: "İsabet",
    summary: "Geçmiş koşuların skorlarının sonraki 1/7/30 günlük fiyat getirileriyle karşılaştırılması.",
    points: [
      "İsabet oranı yalnızca yön sinyali üreten koşular (|skor| ≥ 0,05) üzerinden hesaplanır.",
      "Getiri, koşu anındaki fiyattan vade sonundaki günlük kapanışa göre ölçülür; işlem maliyeti içermez.",
      "Yükseliş/düşüş sinyallerinin ortalama getirisi ayrı gösterilir; nötr koşular yön tahmini sayılmaz.",
      "Örneklem küçükken oranlar oynaktır; yorum için en az 10–15 yönlü koşu birikmesini bekleyin.",
      "Vadesi dolmamış koşular tabloda '—' görünür ve zamanla otomatik dolar.",
    ],
  },
  report: {
    title: "Rapor",
    summary: "Derin araştırma sonunda üretilen Markdown raporu; kopyalanabilir, indirilebilir ve yazdırılabilir.",
    points: [
      "Rapor; yönetici özeti, olasılık/aralık tahmini, 66 kriterin bulguları ve kaynakça bölümlerinden oluşur.",
      "Bağlam istatistikleri hangi veri grubundan kaç kaydın kullanıldığını gösterir.",
      "Markdown İndir ile dosyayı kaydedebilir, Yazdır/PDF ile arşivleyebilirsiniz.",
    ],
  },
  prompt: {
    title: "Prompt Çıktısı",
    summary: "Raporun ChatGPT, Claude, Codex veya OpenRouter gibi araçlara yapıştırılmaya hazır istem metni.",
    points: [
      "Prompt; varlık özeti, modül bulguları, 66 kriter bağlamı ve beklenen çıktı şemasını içerir.",
      "OpenRouter anahtarı tanımlıysa sistem doğrudan yanıt üretebilir; değilse yalnızca prompt oluşturulur.",
      "Metnin uzunluğu karakter sayısı olarak araç çubuğunda gösterilir.",
    ],
  },
  rag: {
    title: "Kaynak Arama",
    summary: "Yerel bilgi tabanında (haberler, notlar, geçmiş çalışmalar) anlamsal arama.",
    points: [
      "Arama; SQLite FTS5 tam metin ve LanceDB vektör indeksini birlikte kullanır.",
      "'Ara' ilgili pasajları getirir; 'AI ile Yanıtla' bu pasajlardan yanıt ya da prompt üretir.",
      "Sonuçlardaki sayı benzerlik skorudur; büyük olan daha alakalı anlamına gelir.",
    ],
  },
  history: {
    title: "Rapor Arşivi",
    summary: "Geçmiş derin araştırma raporları; bir satıra tıklayınca içeriği açılır.",
    points: [
      "Her satır varlık, dosya adı ve oluşturma zamanını gösterir.",
      "Seçilen rapor Markdown olarak görüntülenir; yazdırabilir veya Kapat ile kapatabilirsiniz.",
      "Yenile düğmesi arşiv listesini sunucudan tekrar çeker.",
    ],
  },
};

function PageIntro({ id }) {
  const intro = TAB_INTROS[id];
  if (!intro) return null;
  return (
    <div className="page-intro">
      <div className="page-intro-head">
        <IconInfo width={15} height={15} />
        <b>{intro.title}</b>
        <span>{intro.summary}</span>
      </div>
      <details className="page-intro-more">
        <summary>Bu sayfa nasıl okunur?</summary>
        <ul>
          {intro.points.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}

function scoreColor(value) {
  if (value === null || value === undefined) return "neutral";
  if (value > 0.15) return "positive";
  if (value < -0.15) return "negative";
  return "neutral";
}

function StatusBadge({ status }) {
  const meta = STATUS_META[status] || STATUS_META.no_data;
  const Icon = meta.icon;
  return (
    <span className={`status-badge tone-${meta.tone}`}>
      <Icon width={13} height={13} />
      {meta.label}
    </span>
  );
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

function SnapshotCard({ data, busy }) {
  if (!data) return null;
  const s = data.snapshot;
  const g = data.global;
  const stats = [
    ["Fiyat", price(s.price_usd), null],
    ["Piyasa değeri", money(s.market_cap_usd), null],
    ["Sıra", s.rank ? `#${s.rank}` : DASH, null],
    ["24s hacim", money(s.volume_24h_usd), null],
    ["24s", pct(s.change_24h_pct, { signed: true }), (s.change_24h_pct ?? 0) >= 0 ? "up" : "down"],
    ["7g", pct(s.change_7d_pct, { signed: true }), (s.change_7d_pct ?? 0) >= 0 ? "up" : "down"],
    ["30g", pct(s.change_30d_pct, { signed: true }), (s.change_30d_pct ?? 0) >= 0 ? "up" : "down"],
    ["ATH uzaklığı", pct(s.ath_change_pct), "down"],
    ["ATL uzaklığı", pct(s.atl_change_pct), "up"],
    ["BTC dominansı", g?.btc_dominance != null ? `%${g.btc_dominance.toFixed(1)}` : DASH, null],
    ["ETH dominansı", g?.eth_dominance != null ? `%${g.eth_dominance.toFixed(1)}` : DASH, null],
    ["Toplam piyasa değeri", money(g?.total_market_cap_usd), null],
  ];
  return (
    <div
      className={`snapshot-grid ${busy ? "is-loading" : ""}`}
      title={`Tam değerler: fiyat ${s.price_usd} USD · piyasa değeri ${s.market_cap_usd} USD`}
    >
      {stats.map(([label, value, tone]) => (
        <div className="stat" key={label}>
          <span className="stat-label">{label}</span>
          <span className={`stat-value ${tone || ""}`}>{value}</span>
        </div>
      ))}
    </div>
  );
}

function ModuleStatusStrip({ modules, results, selected, busy }) {
  const resultMap = useMemo(() => new Map(results.map((r) => [r.key, r])), [results]);
  if (!modules.length) return null;
  const executed = modules.filter((m) => resultMap.has(m.key)).length;

  const scrollTo = (key) => {
    const element = document.getElementById(`analysis-${key}`);
    if (element) element.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <div className="module-panel card">
      <div className="module-panel-head">
        <h3>
          Analiz Modülleri
          <span className="muted">
            {executed}/{modules.length} modül çalıştırıldı
          </span>
        </h3>
        <div className="legend">
          <span className="legend-item tone-ok"><i /> Tam</span>
          <span className="legend-item tone-warn"><i /> Kısmi</span>
          <span className="legend-item tone-muted"><i /> Veri yok</span>
          <span className="legend-item tone-idle"><i /> Çalıştırılmadı</span>
        </div>
      </div>
      <details className="module-help">
        <summary>Modüller ne yapar?</summary>
        <ul>
          {modules.map((module) => (
            <li key={module.key}>
              <b>{module.title}</b>
              {module.description ? ` — ${module.description}` : ""}
            </li>
          ))}
        </ul>
      </details>
      <div className="module-strip">
        {modules.map((module, index) => {
          const result = resultMap.get(module.key);
          const status = result
            ? result.status
            : busy
              ? (selected.includes(module.key) ? "pending" : "idle")
              : (selected.includes(module.key) ? "not_run" : "idle");
          const meta = STATUS_META[status];
          const Icon = meta.icon;
          return (
            <button
              key={module.key}
              className={`module-chip tone-${meta.tone} ${result ? "clickable" : ""}`}
              onClick={() => result && scrollTo(module.key)}
              title={[module.description, result ? "Sonuçlara git" : meta.label].filter(Boolean).join(" · ")}
            >
              <span className="module-no">{index + 1}</span>
              <span className="module-name">{module.title}</span>
              <span className="module-status">
                <Icon width={12} height={12} />
                {meta.label}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function AnalysisCard({ result, description }) {
  const reasons = result.data?.reasons || [];
  const meta = STATUS_META[result.status] || STATUS_META.no_data;
  const Icon = meta.icon;
  const executedText = {
    ok: "Modül çalıştırıldı",
    partial: "Modül çalıştırıldı (kısmi veri)",
    no_data: "Modül çalıştı ancak veri bulunamadı",
    error: "Modül hata verdi",
  }[result.status];

  return (
    <div className={`card analysis-card ${scoreColor(result.score)}`} id={`analysis-${result.key}`}>
      <div className={`analysis-status tone-${meta.tone}`}>
        <Icon width={14} height={14} />
        <b>{executedText}</b>
        <span className="muted">
          {meta.label} · Skor {score(result.score)} · Güven {(result.confidence ?? 0).toFixed(2)}
        </span>
      </div>
      <div className="card-head">
        <h3>{result.title}</h3>
        <ScorePill value={result.score} />
      </div>
      {description && <p className="module-desc">{description}</p>}
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
          (item.description_tr || "").toLowerCase().includes(needle) ||
          (item.category || "").toLowerCase().includes(needle) ||
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
          data-search-input
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
                <StatusBadge status={item.status} />
                <ScorePill value={item.score} />
              </div>
            </div>
            {item.description_tr && (
              <p className="item-desc">
                <span className="section-label">Ne araştırılır?</span> {item.description_tr}
              </p>
            )}
            <div className="item-finding">
              <span className="section-label">Bulgu</span>
              <p className="summary clamp-3">{item.summary}</p>
            </div>
            {item.note && (
              <p className="item-note">
                <IconInfo width={12} height={12} /> {item.note}
              </p>
            )}
            <div className="item-footer">
              <span
                className="muted"
                title="Kategori · Ağırlık: kriterin genel skora katkı katsayısı (aynı modül grubunda bir kez sayılır) · Güven: verinin güvenilirliği (0–1)"
              >
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
                <summary>Hesaplanan ham veriyi göster</summary>
                <pre>{JSON.stringify(item.data, null, 2)}</pre>
              </details>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function sourceLabel(item) {
  if (item.source_type === "analysis") return `Analiz modülü · ${item.source_ref}`;
  if (item.source_type === "special") return "Yerel hesaplama motoru";
  if (item.source_type === "news") return `Haber taraması · "${item.query}"`;
  return "Doğrulanabilir ücretsiz veri kaynağı yok";
}

function CriteriaCatalog({ items }) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return items;
    return items.filter(
      (item) =>
        item.title.toLowerCase().includes(needle) ||
        (item.description || "").toLowerCase().includes(needle) ||
        item.category.toLowerCase().includes(needle)
    );
  }, [items, query]);

  return (
    <div>
      <div className="filter-row">
        <input
          className="search-input"
          data-search-input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="66 kriter arasında ara…"
        />
        <span className="muted">{filtered.length} kriter</span>
      </div>
      <div className="items-grid">
        {filtered.map((item) => (
          <div className="card item-card catalog-card" key={item.id}>
            <div className="card-head">
              <h4>
                <span className="item-no">{item.id}</span> {item.title}
              </h4>
              <div className="card-meta">
                <span className="category-chip">{item.category}</span>
                <span className="weight-chip" title="Genel skora katkı katsayısı">
                  Ağırlık {item.weight}
                </span>
              </div>
            </div>
            <p className="item-desc">{item.description}</p>
            {item.note && (
              <p className="item-note">
                <IconInfo width={12} height={12} /> {item.note}
              </p>
            )}
            <div className="item-footer">
              <span className="muted">{sourceLabel(item)}</span>
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

const LOADER_STAGES = [
  "Veri kaynakları taranıyor…",
  "Piyasa verisi ve teknik göstergeler işleniyor…",
  "Haber akışı ve duyarlılık analizi yapılıyor…",
  "Türev ve zincir-üstü veriler toplanıyor…",
  "66 kriter tek tek değerlendiriliyor…",
  "Rapor ve prompt hazırlanıyor…",
];

function ResearchLoader({ message, progress, elapsed, mode }) {
  const [stageIndex, setStageIndex] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setStageIndex((index) => (index + 1) % LOADER_STAGES.length), 3600);
    return () => clearInterval(timer);
  }, []);
  const showJobMessage = message && progress > 0 && progress < 100;
  const display = showJobMessage ? message : mode === "analyze" ? "Analiz modülleri çalıştırılıyor…" : LOADER_STAGES[stageIndex];
  const value = progress > 0 ? progress : null;

  return (
    <div className="research-loader">
      <div className="orbital" aria-hidden="true">
        <span className="ring ring-1" />
        <span className="ring ring-2" />
        <span className="ring ring-3" />
        <span className="orbit orbit-1"><i /></span>
        <span className="orbit orbit-2"><i /></span>
        <span className="orbit orbit-3"><i /></span>
        <span className="orbital-core">
          <IconSparkles width={22} height={22} />
        </span>
      </div>
      <div className="loader-info">
        <h3>{display}</h3>
        <div className={`job-bar ${value === null ? "indeterminate" : ""}`}>
          <div className="job-fill" style={value === null ? undefined : { width: `${value}%` }} />
        </div>
        <span className="muted small">
          {mode === "deep"
            ? `Derin araştırma sürüyor · Süre ${formatDuration(elapsed)} · Sayfayı kapatmayın`
            : "İstek işleniyor…"}
        </span>
      </div>
    </div>
  );
}

function ShortcutHelp({ open, onClose }) {
  if (!open) return null;
  const shortcuts = [
    ["/", "Aktif sekmedeki arama alanına git"],
    ["Esc", "Alanı bırak / pencereyi kapat"],
    ["?", "Bu yardımı aç veya kapat"],
    ["⌘ / Ctrl + Enter", "Derin araştırmayı başlat"],
    ["Enter", "Varlık alanında piyasa özetini yükle (dropdown'da seçimi onaylar)"],
    ["↑ ↓", "Varlık önerileri arasında gezin"],
  ];
  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal" role="dialog" aria-modal="true" aria-label="Klavye kısayolları" onClick={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <h3>Klavye Kısayolları</h3>
          <button className="modal-close" onClick={onClose} aria-label="Kapat">
            <IconX width={15} height={15} />
          </button>
        </div>
        <ul className="shortcut-list">
          {shortcuts.map(([keys, description]) => (
            <li key={keys}>
              <kbd>{keys}</kbd>
              <span>{description}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function Toast({ toast }) {
  if (!toast) return null;
  return (
    <div className={`toast toast-${toast.kind}`} role="status">
      {toast.kind === "success" ? <IconCheck width={15} height={15} /> : <IconAlert width={15} height={15} />}
      {toast.message}
    </div>
  );
}

function EmptyState({ title, children }) {
  return (
    <div className="empty-state">
      <svg width="132" height="76" viewBox="0 0 132 76" className="empty-art" aria-hidden="true">
        <defs>
          <linearGradient id="emptyGradient" x1="0" x2="1">
            <stop offset="0%" stopColor="#4c8dff" />
            <stop offset="100%" stopColor="#7c5cff" />
          </linearGradient>
        </defs>
        <rect x="10" y="34" width="13" height="32" rx="4" fill="url(#emptyGradient)" opacity=".45" />
        <rect x="30" y="22" width="13" height="44" rx="4" fill="url(#emptyGradient)" opacity=".7" />
        <rect x="50" y="42" width="13" height="24" rx="4" fill="url(#emptyGradient)" opacity=".45" />
        <rect x="70" y="12" width="13" height="54" rx="4" fill="url(#emptyGradient)" />
        <rect x="90" y="28" width="13" height="38" rx="4" fill="url(#emptyGradient)" opacity=".7" />
        <circle cx="114" cy="18" r="4.5" fill="#2ecc8f" />
        <circle cx="120" cy="30" r="2.5" fill="#4c8dff" />
      </svg>
      <h3>{title}</h3>
      <div className="muted">{children}</div>
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
  const [toast, setToast] = useState(null);
  const [ragQuery, setRagQuery] = useState("");
  const [ragResults, setRagResults] = useState([]);
  const [ragAnswer, setRagAnswer] = useState(null);
  const [reports, setReports] = useState([]);
  const [reportQuery, setReportQuery] = useState("");
  const [runHistory, setRunHistory] = useState([]);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [ragStats, setRagStats] = useState(null);
  const [selectedReport, setSelectedReport] = useState(null);
  const [copied, setCopied] = useState("");
  const toastTimer = useRef(null);
  const selectionsInitialized = useRef(false);
  const deepResearchRef = useRef(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => {});
    api.analyses().then(setAnalysesList).catch(() => {});
    api.items().then(setItems).catch(() => {});
    api.reports().then(setReports).catch(() => {});
    api.ragStats().then(setRagStats).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectionsInitialized.current && analysesList.length) {
      selectionsInitialized.current = true;
      setSelected(analysesList.map((analysis) => analysis.key));
    }
  }, [analysesList]);

  useEffect(() => {
    if (busy !== "deep" || !jobStartedAt) return undefined;
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - jobStartedAt) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [busy, jobStartedAt]);

  useEffect(() => () => toastTimer.current && clearTimeout(toastTimer.current), []);

  useEffect(() => {
    let cancelled = false;
    api
      .runs(coin)
      .then((rows) => {
        if (!cancelled) setRunHistory(rows);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [coin, deep]);

  useEffect(() => {
    const handler = (event) => {
      const target = event.target;
      const typing =
        target &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if (event.key === "/" && !typing) {
        const field = document.querySelector("section.content [data-search-input], .toolbar input");
        if (field) {
          event.preventDefault();
          field.focus();
        }
      } else if (event.key === "Escape") {
        if (typing && target.blur) target.blur();
        setShowShortcuts(false);
      } else if (event.key === "?" && !typing) {
        event.preventDefault();
        setShowShortcuts((value) => !value);
      } else if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        deepResearchRef.current?.();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const showToast = (message, kind = "success") => {
    setToast({ message, kind });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 4200);
  };

  const toggleAnalysis = (key) => {
    setSelected((prev) => (prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key]));
  };

  const selectAllAnalyses = () => setSelected(analysesList.map((analysis) => analysis.key));
  const clearAnalyses = () => setSelected([]);

  const loadSnapshot = async (coinOverride) => {
    const target = String(coinOverride ?? coin ?? "").trim();
    if (!target) return;
    setBusy("snapshot");
    setError("");
    try {
      setSnapshotData(await api.snapshot(target));
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
      showToast(`${analysis.analyses.length} modül tamamlandı`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  };

  const runDeepResearch = async () => {
    if (busy) return;
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
      let pollFailures = 0;
      while (state.status === "queued" || state.status === "running") {
        await new Promise((resolve) => setTimeout(resolve, 2500));
        try {
          state = await api.jobStatus(state.job_id);
          pollFailures = 0;
        } catch (pollError) {
          // Sunucu kisa sureli yogun olabilir (embedding yuklemesi vb.);
          // birkac ust uste hatadan sonra gerçekten vazgec.
          pollFailures += 1;
          if (pollFailures >= 4) throw pollError;
          setJob((previous) => ({
            ...(previous || state),
            job_id: state.job_id,
            message: "Sunucu yanıtı bekleniyor; bağlantı yeniden kuruluyor…",
          }));
          continue;
        }
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
      showToast(`${result.run.coin.name} araştırması tamamlandı`);
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
  const deepBusy = busy === "deep";
  deepResearchRef.current = runDeepResearch;

  const filteredReports = useMemo(() => {
    const needle = reportQuery.trim().toLowerCase();
    if (!needle) return reports;
    return reports.filter(
      (report) =>
        report.name.toLowerCase().includes(needle) || (report.coin || "").toLowerCase().includes(needle)
    );
  }, [reports, reportQuery]);

  return (
    <div className="app">
      <aside className="sidebar">
        <h1>
          Crypto<span>DeepResearch</span>
        </h1>
        <p className="muted small">Kripto varlıklar için yerel RAG ve derin araştırma altyapısı</p>

        <div className="field">
          <span>Varlık (sembol veya CoinGecko kimliği)</span>
          <CoinSelect
            defaultValue={coin}
            placeholder="örn. bitcoin, eth, chainlink"
            onManualChange={(value) => setCoin(value)}
            onSelect={(suggestion) => {
              setCoin(suggestion.id);
              loadSnapshot(suggestion.id);
            }}
            onSubmit={(value) => {
              setCoin(value);
              loadSnapshot(value);
            }}
          />
        </div>

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
          <div className="field-head">
            <span>Analiz Modülleri</span>
            <span className="muted">
              {selected.length}/{analysesList.length || 10} seçili
            </span>
          </div>
          <div className="field-actions">
            <button type="button" className="mini-btn" onClick={selectAllAnalyses}>
              Tümünü seç
            </button>
            <button type="button" className="mini-btn" onClick={clearAnalyses}>
              Temizle
            </button>
          </div>
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
          {busy === "analyze" ? (
            <>
              <span className="spinner" /> Analiz çalışıyor…
            </>
          ) : (
            <>
              <IconPlay width={13} height={13} /> Analiz Çalıştır
            </>
          )}
        </button>
        <button className="accent" onClick={runDeepResearch} disabled={!!busy}>
          {busy === "deep" ? (
            <>
              <span className="spinner" /> Derin araştırma sürüyor…
            </>
          ) : (
            <>
              <IconSparkles width={14} height={14} /> Derin Araştırma Başlat
            </>
          )}
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
          <button className="mini-btn" onClick={() => setShowShortcuts(true)}>
            Klavye kısayolları (?)
          </button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <nav className="tabs">
            {TABS.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  className={tab === item.id ? "active" : ""}
                  onClick={() => setTab(item.id)}
                >
                  <Icon width={14} height={14} />
                  {item.label}
                </button>
              );
            })}
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

        {error && (
          <div className="error">
            <IconAlert width={15} height={15} /> {error}
          </div>
        )}
        {(deepBusy || busy === "analyze") && (
          <ResearchLoader
            message={deepBusy ? job?.message : undefined}
            progress={deepBusy ? (job?.progress ?? 0) : 0}
            elapsed={elapsed}
            mode={deepBusy ? "deep" : "analyze"}
          />
        )}

        <section className="content">
          {tab === "overview" && (
            <>
              <PageIntro id="overview" />
              <SnapshotCard data={snapshotData} busy={busy === "snapshot"} />
              {(snapshotData || analysisResults.length > 0) && (
                <PriceChart coin={coin} defaultTimeframe={timeframe} />
              )}
              {run && (
                <div className="card result-summary">
                  <h3>Olasılık Dağılımı</h3>
                  <ProbabilityBar up={run.up_probability} down={run.down_probability} />
                  <div className="range-line">
                    Beklenen fiyat aralığı: <b>{priceRange(run.expected_low, run.expected_high)}</b>
                  </div>
                  <ScoreDistribution items={run.items} />
                </div>
              )}
              {runHistory.length >= 2 && (
                <div className="card history-card">
                  <div className="card-head">
                    <h3>Skor Geçmişi</h3>
                    <span className="muted">
                      {runHistory.length} koşu ·{" "}
                      {snapshotData?.snapshot?.coin?.symbol?.toUpperCase() || coin.toUpperCase()}
                    </span>
                  </div>
                  <ScoreHistoryChart runs={runHistory} />
                </div>
              )}
              {analysesList.length > 0 && (snapshotData || analysisResults.length > 0 || busy) && (
                <ModuleStatusStrip
                  modules={analysesList}
                  results={analysisResults}
                  selected={selected}
                  busy={!!busy}
                />
              )}
              {!snapshotData && !busy && (
                <EmptyState title="Araştırmaya başlayın">
                  Sol panelden bir varlık seçin; ardından <b>Analiz Çalıştır</b> ile modülleri veya{" "}
                  <b>Derin Araştırma Başlat</b> ile 66 kriteri çalıştırın.
                </EmptyState>
              )}
              {(busy === "analyze" || busy === "deep") && analysisResults.length === 0 && <Skeleton />}
              <div className="grid">
                {analysisResults.map((result) => (
                  <AnalysisCard
                    key={result.key || result.title}
                    result={result}
                    description={analysesList.find((module) => module.key === result.key)?.description}
                  />
                ))}
              </div>
            </>
          )}

          {tab === "findings" && (
            <>
              <PageIntro id="findings" />
              {!run && (
                <>
                  <EmptyState title="Henüz araştırma çalıştırılmadı">
                    Aşağıda <b>Derin Araştırma Başlat</b> ile çalıştırılacak 66 kriter, her birinin neyi
                    araştırdığıyla birlikte listeleniyor.
                  </EmptyState>
                  {items.length > 0 && <CriteriaCatalog items={items} />}
                </>
              )}
              {run && <FindingsTable items={run.items} />}
            </>
          )}

          {tab === "accuracy" && (
            <>
              <PageIntro id="accuracy" />
              <AccuracyPanel coin={coin} />
            </>
          )}

          {tab === "report" && (
            <>
              <PageIntro id="report" />
              {!deep && (
                <EmptyState title="Rapor bekleniyor">
                  Derin araştırma tamamlandığında rapor burada görüntülenir.
                </EmptyState>
              )}
              {deep && (
                <>
                  <div className="toolbar">
                    <button onClick={copyReport}>
                      <IconCopy width={14} height={14} />
                      {copied === "report" ? "Kopyalandı" : "Kopyala"}
                    </button>
                    <button onClick={downloadReport}>
                      <IconDownload width={14} height={14} /> Markdown İndir
                    </button>
                    <button onClick={() => window.print()}>
                      <IconPrinter width={14} height={14} /> Yazdır / PDF
                    </button>
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
              <PageIntro id="prompt" />
              {!deep && (
                <EmptyState title="Prompt bekleniyor">
                  Derin araştırma tamamlandığında harici AI araçları için prompt üretilir.
                </EmptyState>
              )}
              {deep && (
                <>
                  <div className="toolbar">
                    <button onClick={copyPrompt}>
                      <IconCopy width={14} height={14} />
                      {copied === "prompt" ? "Kopyalandı" : "Kopyala"}
                    </button>
                    <button onClick={downloadPrompt}>
                      <IconDownload width={14} height={14} /> İndir
                    </button>
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
              <PageIntro id="rag" />
              <div className="toolbar">
                <input
                  value={ragQuery}
                  data-search-input
                  onChange={(event) => setRagQuery(event.target.value)}
                  placeholder="Araştırma notlarında ve haberlerde ara…"
                  onKeyDown={(event) => event.key === "Enter" && runRagSearch("rag-search")}
                />
                <button onClick={() => runRagSearch("rag-search")} disabled={!!busy}>
                  <IconSearch width={14} height={14} /> Ara
                </button>
                <button onClick={() => runRagSearch("rag-ask")} disabled={!!busy}>
                  <IconSparkles width={14} height={14} />
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
              <PageIntro id="history" />
              <div className="toolbar">
                <input
                  className="search-input"
                  data-search-input
                  value={reportQuery}
                  onChange={(event) => setReportQuery(event.target.value)}
                  placeholder="Rapor veya coin ara…"
                />
                <button onClick={() => api.reports().then(setReports)}>
                  <IconRefresh width={14} height={14} /> Yenile
                </button>
                <span className="muted">
                  {filteredReports.length}/{reports.length} rapor
                </span>
              </div>
              {filteredReports.length === 0 && (
                <EmptyState title="Eşleşen rapor yok">
                  {reports.length === 0
                    ? "Derin araştırma tamamlandığında raporlar burada arşivlenir."
                    : "Arama ölçütünü değiştirin veya Yenile düğmesini kullanın."}
                </EmptyState>
              )}
              <div className="reports-list">
                {filteredReports.map((report) => (
                  <button
                    key={report.name}
                    className="report-row"
                    onClick={async () => setSelectedReport(await api.report(report.name))}
                  >
                    <span className="report-coin">
                      <IconCoins width={14} height={14} />
                      {report.coin}
                    </span>
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
                    <button onClick={() => window.print()}>
                      <IconPrinter width={14} height={14} /> Yazdır / PDF
                    </button>
                    <button onClick={() => setSelectedReport(null)}>Kapat</button>
                  </div>
                  <Markdown>{selectedReport.markdown}</Markdown>
                </>
              )}
            </>
          )}
        </section>
      </main>

      <ShortcutHelp open={showShortcuts} onClose={() => setShowShortcuts(false)} />
      <Toast toast={toast} />
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
