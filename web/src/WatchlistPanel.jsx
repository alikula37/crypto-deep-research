import { useEffect, useRef, useState } from "react";
import CoinSelect from "./CoinSelect.jsx";
import { api } from "./api.js";
import { formatDateTime, price } from "./format.js";
import { IconBell, IconPlay, IconRefresh, IconSend, IconX } from "./icons.jsx";

const ALARM_KEY = "cdr-alarms";

const ALARM_TYPES = {
  price_above: { label: "Fiyat ≥", hint: "USD" },
  price_below: { label: "Fiyat ≤", hint: "USD" },
  score_above: { label: "Skor ≥", hint: "-1…+1" },
  score_below: { label: "Skor ≤", hint: "-1…+1" },
  up_above: { label: "Yükseliş olasılığı ≥", hint: "%" },
};

function loadAlarms() {
  try {
    return JSON.parse(localStorage.getItem(ALARM_KEY) || "[]");
  } catch {
    return [];
  }
}

function alarmValue(alarm, data) {
  if (alarm.type.startsWith("price")) return data.price;
  if (alarm.type.startsWith("score")) return data.score;
  return data.up;
}

function alarmHit(alarm, value) {
  if (value === null || value === undefined) return false;
  if (alarm.type === "price_above" || alarm.type === "score_above") return value >= alarm.value;
  if (alarm.type === "price_below" || alarm.type === "score_below") return value <= alarm.value;
  return value >= alarm.value;
}

export default function WatchlistPanel({ initialCoin, onNotify }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [alarms, setAlarms] = useState(loadAlarms);
  const [telegram, setTelegram] = useState(null);
  const [telegramToken, setTelegramToken] = useState("");
  const [telegramBusy, setTelegramBusy] = useState(false);
  const [alarmForm, setAlarmForm] = useState({
    coin: initialCoin || "bitcoin",
    type: "price_above",
    value: "",
  });
  const alarmsRef = useRef(alarms);
  alarmsRef.current = alarms;
  const notifyRef = useRef(onNotify);
  notifyRef.current = onNotify;

  const load = () => {
    setLoading(true);
    api
      .watchlist()
      .then(setEntries)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  useEffect(() => {
    const loadTelegram = () => api.telegramStatus().then(setTelegram).catch(() => {});
    loadTelegram();
    const timer = setInterval(loadTelegram, 10000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    localStorage.setItem(ALARM_KEY, JSON.stringify(alarms));
  }, [alarms]);

  useEffect(() => {
    const enabled = alarms.filter((alarm) => alarm.enabled);
    if (!enabled.length) return undefined;
    const check = async () => {
      const coins = [...new Set(alarmsRef.current.filter((a) => a.enabled).map((a) => a.coin))];
      const cache = {};
      await Promise.all(
        coins.map(async (coin) => {
          try {
            const snapshot = await api.snapshot(coin);
            cache[coin] = { ...(cache[coin] || {}), price: snapshot.snapshot.price_usd };
          } catch {
            // fiyat alinamadi; diger kosullar denenir
          }
          try {
            const runs = await api.runs(coin);
            const last = runs[runs.length - 1];
            if (last) cache[coin] = { ...(cache[coin] || {}), score: last.weighted_score, up: last.up_probability };
          } catch {
            // kosu verisi yok
          }
        })
      );
      setAlarms((previous) =>
        previous.map((alarm) => {
          if (!alarm.enabled) return alarm;
          const data = cache[alarm.coin];
          if (!data) return alarm;
          const value = alarmValue(alarm, data);
          const hit = alarmHit(alarm, value);
          if (hit && !alarm.triggered) {
            const message = `${alarm.coin.toUpperCase()} alarmı: ${ALARM_TYPES[alarm.type].label} ${alarm.value} (şu an ${value})`;
            if ("Notification" in window && Notification.permission === "granted") {
              new Notification("Crypto Deep Research", { body: message });
            }
            notifyRef.current?.(message);
            return { ...alarm, triggered: Date.now() };
          }
          if (!hit && alarm.triggered) return { ...alarm, triggered: null };
          return alarm;
        })
      );
    };
    check();
    const timer = setInterval(check, 60000);
    return () => clearInterval(timer);
  }, [alarms]);

  const addToWatchlist = async (coin) => {
    if (!coin?.id) return;
    setError("");
    try {
      await api.watchlistAdd({ coin: coin.id, symbol: coin.symbol, name: coin.name });
      load();
      onNotify?.(`${coin.name || coin.id} takip listesine eklendi`);
    } catch (err) {
      setError(err.message);
    }
  };

  const updateEntry = async (coin, payload) => {
    setEntries((previous) =>
      previous.map((entry) => (entry.coin === coin ? { ...entry, ...payload } : entry))
    );
    try {
      await api.watchlistUpdate(coin, payload);
    } catch (err) {
      setError(err.message);
      load();
    }
  };

  const removeEntry = async (coin) => {
    try {
      await api.watchlistRemove(coin);
      setEntries((previous) => previous.filter((entry) => entry.coin !== coin));
    } catch (err) {
      setError(err.message);
    }
  };

  const runNow = async (coin) => {
    setError("");
    try {
      const job = await api.watchlistRun(coin);
      onNotify?.(`${coin.toUpperCase()} araştırması başlatıldı (${job.status})`);
    } catch (err) {
      setError(err.message);
    }
  };

  const addAlarm = async () => {
    const value = Number(alarmForm.value);
    if (!alarmForm.coin || Number.isNaN(value)) return;
    if ("Notification" in window && Notification.permission === "default") {
      try {
        await Notification.requestPermission();
      } catch {
        // bildirim izni alinamadi; uygulama ici bildirim kullanilir
      }
    }
    setAlarms((previous) => [
      ...previous,
      {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        coin: alarmForm.coin,
        type: alarmForm.type,
        value,
        enabled: true,
        triggered: null,
      },
    ]);
    setAlarmForm((previous) => ({ ...previous, value: "" }));
  };

  const toggleAlarm = (id) =>
    setAlarms((previous) =>
      previous.map((alarm) =>
        alarm.id === id
          ? { ...alarm, enabled: !alarm.enabled, triggered: alarm.enabled ? null : alarm.triggered }
          : alarm
      )
    );

  const removeAlarm = (id) => setAlarms((previous) => previous.filter((alarm) => alarm.id !== id));

  const startTelegram = async () => {
    setTelegramBusy(true);
    setError("");
    try {
      setTelegram(await api.telegramStart(telegramToken.trim()));
      setTelegramToken("");
      notifyRef.current?.("Telegram botu başlatıldı");
    } catch (err) {
      setError(err.message);
    } finally {
      setTelegramBusy(false);
    }
  };

  const stopTelegram = async () => {
    setTelegramBusy(true);
    setError("");
    try {
      setTelegram(await api.telegramStop());
      notifyRef.current?.("Telegram botu durduruldu");
    } catch (err) {
      setError(err.message);
    } finally {
      setTelegramBusy(false);
    }
  };

  return (
    <div>
      {error && <div className="error">{error}</div>}

      <div className="card watchlist-card">
        <div className="card-head">
          <h3>Takip Listesi</h3>
          <span className="muted">Günde bir otomatik derin araştırma (ayar: CDR_WATCHLIST_AUTO_RUN_HOURS)</span>
        </div>
        <div className="toolbar">
          <CoinSelect placeholder="Takip listesine coin ekle…" onSelect={addToWatchlist} />
          <button onClick={load} disabled={loading}>
            <IconRefresh width={14} height={14} /> Yenile
          </button>
          <span className="muted">{entries.length} coin</span>
        </div>
        {entries.length === 0 && (
          <p className="muted">
            Takip listesi boş. Eklediğiniz coinler için sistem günde bir kez otomatik derin araştırma
            çalıştırır ve rapor arşivine ekler.
          </p>
        )}
        {entries.map((entry) => (
          <div className="watchlist-row" key={entry.coin}>
            <span className="watchlist-symbol">{entry.symbol || entry.coin}</span>
            <span className="watchlist-name">{entry.name || entry.coin}</span>
            <label className="watchlist-field">
              <span className="muted">Profil</span>
              <select
                value={entry.profile}
                onChange={(event) => updateEntry(entry.coin, { profile: event.target.value })}
              >
                <option value="balanced">Dengeli</option>
                <option value="conservative">Muhafazakâr</option>
                <option value="aggressive">Agresif</option>
              </select>
            </label>
            <label className="watchlist-field">
              <span className="muted">Otomatik</span>
              <input
                type="checkbox"
                checked={entry.auto_run}
                onChange={(event) => updateEntry(entry.coin, { auto_run: event.target.checked })}
              />
            </label>
            <span className="muted watchlist-last">
              Son koşu: {entry.last_run_at ? formatDateTime(entry.last_run_at * 1000) : "—"}
            </span>
            <button className="mini-btn" onClick={() => runNow(entry.coin)} title="Şimdi çalıştır">
              <IconPlay width={12} height={12} /> Çalıştır
            </button>
            <button className="mini-btn" onClick={() => removeEntry(entry.coin)} title="Listeden çıkar">
              <IconX width={12} height={12} />
            </button>
          </div>
        ))}
      </div>

      <div className="card alarms-card">
        <div className="card-head">
          <h3>
            <IconBell width={15} height={15} /> Alarmlar
          </h3>
          <span className="muted">
            Tarayıcı bildirimi + uygulama içi uyarı · sayfa açıkken dakikada bir kontrol edilir
          </span>
        </div>
        <div className="alarm-form">
          <CoinSelect
            defaultValue={alarmForm.coin}
            placeholder="Coin"
            onManualChange={(value) => setAlarmForm((previous) => ({ ...previous, coin: value.trim().toLowerCase() }))}
            onSelect={(coin) => setAlarmForm((previous) => ({ ...previous, coin: coin.id }))}
          />
          <select
            value={alarmForm.type}
            onChange={(event) => setAlarmForm((previous) => ({ ...previous, type: event.target.value }))}
          >
            {Object.entries(ALARM_TYPES).map(([key, config]) => (
              <option key={key} value={key}>
                {config.label}
              </option>
            ))}
          </select>
          <input
            type="number"
            step="any"
            placeholder={ALARM_TYPES[alarmForm.type].hint}
            value={alarmForm.value}
            onChange={(event) => setAlarmForm((previous) => ({ ...previous, value: event.target.value }))}
            onKeyDown={(event) => event.key === "Enter" && addAlarm()}
          />
          <button onClick={addAlarm} disabled={!alarmForm.coin || alarmForm.value === ""}>
            Alarm Ekle
          </button>
        </div>
        {alarms.length === 0 && (
          <p className="muted">
            Örnek: BTC fiyatı 80.000 USD üzerine çıkınca, skor +0,4 üzerine çıkınca veya yükseliş
            olasılığı %70'i geçince haber ver.
          </p>
        )}
        {alarms.map((alarm) => (
          <div className={`alarm-row ${alarm.triggered ? "triggered" : ""}`} key={alarm.id}>
            <label className="watchlist-field">
              <input type="checkbox" checked={alarm.enabled} onChange={() => toggleAlarm(alarm.id)} />
            </label>
            <span className="watchlist-symbol">{alarm.coin.toUpperCase()}</span>
            <span>
              {ALARM_TYPES[alarm.type].label} <b>{alarm.value}</b>
            </span>
            {alarm.triggered && (
              <span className="alarm-triggered">
                tetiklendi · {formatDateTime(alarm.triggered)}
              </span>
            )}
            <span className="alarm-price muted">
              {alarm.type.startsWith("price") ? price(alarm.value) : ""}
            </span>
            <button className="mini-btn" onClick={() => removeAlarm(alarm.id)}>
              <IconX width={12} height={12} />
            </button>
          </div>
        ))}
      </div>

      <div className="card telegram-card">
        <div className="card-head">
          <h3>
            <IconSend width={15} height={15} /> Telegram Botu
          </h3>
          <span className={`status-badge tone-${telegram?.running ? "ok" : telegram?.error ? "error" : "idle"}`}>
            {telegram?.running
              ? `Çalışıyor${telegram.username ? ` · @${telegram.username}` : ""}`
              : telegram?.error
                ? "Hata"
                : "Durdu"}
          </span>
        </div>
        {telegram?.error && <p className="muted small">{telegram.error}</p>}
        <div className="alarm-form">
          <input
            type="password"
            autoComplete="off"
            placeholder={
              telegram?.token_configured
                ? "CDR_TELEGRAM_TOKEN tanımlı (değiştirmek için yeni token girin)"
                : "Bot tokeni (BotFather)"
            }
            value={telegramToken}
            onChange={(event) => setTelegramToken(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && startTelegram()}
          />
          <button onClick={startTelegram} disabled={telegramBusy || telegram?.running}>
            {telegramBusy && !telegram?.running ? <span className="spinner" /> : null} Başlat
          </button>
          <button onClick={stopTelegram} disabled={telegramBusy || !telegram?.running}>
            Durdur
          </button>
        </div>
        <p className="muted small">
          Komutlar: /fiyat &lt;coin&gt; · /skor &lt;coin&gt; · /rapor &lt;coin&gt; · /arastir &lt;coin&gt; [profil] · /yardim.
          Bot, sunucu çalıştığı sürece yanıt verir; kalıcı çalıştırma için <code>cdr telegram</code> veya{" "}
          <code>CDR_TELEGRAM_AUTOSTART=true</code> kullanın.
        </p>
      </div>
    </div>
  );
}
