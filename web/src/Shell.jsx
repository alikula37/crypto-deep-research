import CoinSelect from "./CoinSelect.jsx";
import { price } from "./format.js";
import { IconCommand, IconPlay, IconSettings, IconSliders, IconSparkles } from "./icons.jsx";
import { GROUPS, TAB_LABELS } from "./navigation.js";

export function RunBar({
  coin,
  onCoinManual,
  onCoinSelect,
  onCoinSubmit,
  livePrice,
  change24h,
  timeframe,
  onTimeframe,
  profile,
  onProfile,
  profilesList,
  selectedCount,
  moduleCount,
  onOpenSettings,
  onRunAnalyze,
  onRunDeep,
  busy,
  onOpenPalette,
  verdict,
}) {
  const timeframes = ["15m", "30m", "1h", "4h", "1d", "1w"];
  return (
    <header className="runbar">
      <div className="runbar-brand">
        Crypto<span>Research</span>
      </div>

      <button className="runbar-command" onClick={onOpenPalette} title="Komut paleti (⌘K / Ctrl+K)">
        <IconCommand width={13} height={13} />
        <span>Ara veya komut çalıştır…</span>
        <kbd>⌘K</kbd>
      </button>

      <div className="runbar-group">
        <CoinSelect
          key={coin}
          defaultValue={coin}
          placeholder="Varlık ara…"
          onManualChange={onCoinManual}
          onSelect={onCoinSelect}
          onSubmit={onCoinSubmit}
        />
        {livePrice && (
          <span className={`runbar-price ${(change24h ?? 0) >= 0 ? "up" : "down"}`}>
            {livePrice}
          </span>
        )}
      </div>

      <label className="runbar-field">
        <span>TF</span>
        <select value={timeframe} onChange={(event) => onTimeframe(event.target.value)}>
          {timeframes.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>

      <label className="runbar-field">
        <span>Profil</span>
        <select value={profile} onChange={(event) => onProfile(event.target.value)}>
          {(profilesList.length
            ? profilesList
            : [
                { key: "balanced", label: "Dengeli" },
                { key: "conservative", label: "Muhafazakâr" },
                { key: "aggressive", label: "Agresif" },
              ]
          ).map((item) => (
            <option key={item.key} value={item.key}>
              {item.label}
            </option>
          ))}
        </select>
      </label>

      <button className="runbar-modules" onClick={onOpenSettings} title="Modüller ve gelişmiş ayarlar">
        <IconSliders width={13} height={13} />
        Modüller <b>{selectedCount}/{moduleCount || 10}</b>
      </button>

      <div className="runbar-actions">
        <button
          className="primary"
          onClick={onRunAnalyze}
          disabled={!!busy || selectedCount === 0}
          title={selectedCount === 0 ? "En az bir analiz modülü seçin" : "Analiz çalıştır"}
        >
          {busy === "analyze" ? (
            <>
              <span className="spinner" /> Analiz…
            </>
          ) : (
            <>
              <IconPlay width={12} height={12} /> Analiz
            </>
          )}
        </button>
        <button
          className="accent"
          onClick={onRunDeep}
          disabled={!!busy || selectedCount === 0}
          title={selectedCount === 0 ? "En az bir analiz modülü seçin" : "Derin araştırma başlat"}
        >
          {busy === "deep" ? (
            <>
              <span className="spinner" /> Araştırma…
            </>
          ) : (
            <>
              <IconSparkles width={13} height={13} /> Derin Araştırma
            </>
          )}
        </button>
        <button className="ghost" onClick={onOpenSettings} title="Ayarlar">
          <IconSettings width={14} height={14} />
        </button>
      </div>

      {verdict && <div className="runbar-verdict">{verdict}</div>}
    </header>
  );
}

export function IconRail({ activeGroupId, onSelectGroup, onHelp }) {
  return (
    <nav className="rail" aria-label="Ana bölümler">
      {GROUPS.map((group) => {
        const Icon = group.icon;
        const active = group.id === activeGroupId;
        return (
          <button
            key={group.id}
            className={`rail-item ${active ? "active" : ""}`}
            onClick={() => onSelectGroup(group)}
            aria-current={active ? "page" : undefined}
            title={group.label}
          >
            <Icon width={17} height={17} />
            <span>{group.label}</span>
          </button>
        );
      })}
      <button className="rail-item rail-help" onClick={onHelp} title="Klavye kısayolları (?)">
        <b>?</b>
        <span>Yardım</span>
      </button>
    </nav>
  );
}

export function ViewHeader({ group, tab, onSelectTab }) {
  return (
    <div className="viewheader">
      <h2 className="viewheader-title">{group.label}</h2>
      <div className="subtabs" role="tablist" aria-label={`${group.label} görünümleri`}>
        {group.tabs.map((tabId) => (
          <button
            key={tabId}
            role="tab"
            aria-selected={tab === tabId}
            className={tab === tabId ? "active" : ""}
            onClick={() => onSelectTab(tabId)}
          >
            {TAB_LABELS[tabId] || tabId}
          </button>
        ))}
      </div>
    </div>
  );
}

export function SettingsSheet({
  open,
  onClose,
  analysesList,
  selected,
  onToggle,
  onSelectAll,
  onClear,
  lookback,
  onLookback,
  platform,
  onPlatform,
  language,
  onLanguage,
  health,
  ragStats,
  onShortcuts,
}) {
  if (!open) return null;
  return (
    <div className="sheet-backdrop" onClick={onClose} role="presentation">
      <aside className="sheet" role="dialog" aria-modal="true" aria-label="Modüller ve ayarlar" onClick={(event) => event.stopPropagation()}>
        <div className="sheet-head">
          <h3>Modüller ve Ayarlar</h3>
          <button className="ghost" onClick={onClose} aria-label="Kapat">
            ✕
          </button>
        </div>

        <div className="sheet-section">
          <div className="sheet-section-head">
            <span>Analiz Modülleri</span>
            <span className="muted">
              {selected.length}/{analysesList.length || 10} seçili
            </span>
          </div>
          <div className="field-actions">
            <button type="button" className="mini-btn" onClick={onSelectAll}>
              Tümünü seç
            </button>
            <button type="button" className="mini-btn" onClick={onClear}>
              Temizle
            </button>
          </div>
          <div className="checklist">
            {analysesList.map((analysis) => (
              <label key={analysis.key} className="check">
                <input
                  type="checkbox"
                  checked={selected.includes(analysis.key)}
                  onChange={() => onToggle(analysis.key)}
                />
                <span>{analysis.title}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="sheet-section">
          <div className="sheet-grid">
            <label className="field">
              <span>Geriye Dönük Veri (gün)</span>
              <input
                type="number"
                min="30"
                max="3650"
                value={lookback}
                onChange={(event) => onLookback(event.target.value)}
              />
            </label>
            <label className="field">
              <span>Prompt Hedefi</span>
              <select value={platform} onChange={(event) => onPlatform(event.target.value)}>
                <option value="generic">Genel</option>
                <option value="claude">Claude</option>
                <option value="codex">Codex</option>
                <option value="chatgpt">ChatGPT</option>
              </select>
            </label>
            <label className="field">
              <span>Prompt Dili</span>
              <select value={language} onChange={(event) => onLanguage(event.target.value)}>
                <option value="tr">Türkçe</option>
                <option value="en">İngilizce</option>
              </select>
            </label>
          </div>
        </div>

        <div className="sheet-section">
          <div className="sheet-section-head">
            <span>Sistem Durumu</span>
            <button className="mini-btn" onClick={onShortcuts}>
              Kısayollar (?)
            </button>
          </div>
          {health && (
            <p className="muted small">
              Anahtarlar:{" "}
              {Object.entries(health.keys)
                .filter(([, value]) => value)
                .map(([key]) => key)
                .join(", ") || "tanımlı değil"}{" "}
              · OpenRouter: {health.openrouter ? "aktif" : "pasif"} · Rapor: {health.reports} · Vektör:{" "}
              {ragStats?.vectors ?? 0}
            </p>
          )}
        </div>
      </aside>
    </div>
  );
}
