import { useEffect, useState } from "react";
import { api } from "./api.js";
import { IconRefresh } from "./icons.jsx";

function signedPct(value, digits = 2) {
  if (value === null || value === undefined) return "—";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;
}

function fundingPct(value) {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(4)}%`;
}

function tone(value) {
  if (value === null || value === undefined) return "muted";
  return value >= 0 ? "up" : "down";
}

function sparklinePoints(series) {
  if (!series || series.length < 2) return null;
  const values = series.map((row) => row.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  return values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * 100;
      const y = 30 - ((value - min) / range) * 26;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

export default function CarryPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [stepping, setStepping] = useState(false);
  const [error, setError] = useState("");

  const load = () => {
    setLoading(true);
    api
      .carry()
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const step = async () => {
    setStepping(true);
    setError("");
    try {
      const result = await api.carryStep();
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setStepping(false);
    }
  };

  const reset = async () => {
    if (!window.confirm("Paper takip sıfırlanacak. Emin misiniz?")) return;
    setError("");
    try {
      await api.carryReset();
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const state = data?.state;
  const holdings = state?.holdings || [];
  const ranking = state?.ranking || [];
  const series = data?.series || [];
  const points = sparklinePoints(series);
  const cumulative = state ? state.equity - 1 : null;
  const edge = data?.edge_30d_annual;

  return (
    <div>
      {error && <div className="error">{error}</div>}

      {data?.alert && (
        <div className={`carry-alert ${data.alert.severity}`}>
          <b>{data.alert.severity === "critical" ? "Kritik" : "Uyarı"}:</b> {data.alert.message}
        </div>
      )}

      {!state ? (
        <div className="card carry-empty">
          <h3>Paper takip henüz başlamadı</h3>
          <p className="muted">
            Strateji, fonlaması en yüksek coinlerde long spot + short perp pozisyonu tutar; getiri
            toplanan fonlamadan gelir. Günlük adımı çalıştırınca canlı veriyle izlemeye başlar.
          </p>
          <button onClick={step} disabled={stepping}>
            {stepping ? "Başlatılıyor…" : "Paper takibi başlat"}
          </button>
        </div>
      ) : (
        <>
          <div className="card carry-hero">
            <div className="carry-hero-value">
              <span className="muted">Kümülatif getiri</span>
              <b className={tone(cumulative)}>{signedPct(cumulative)}</b>
              <span className="muted">
                Equity {state.equity.toFixed(4)} · {series.length} gün · başlangıç {series[0]?.as_of}
              </span>
            </div>

            <div className="carry-hero-metrics">
              <div className="carry-metric">
                <span>Günlük</span>
                <b className={tone(state.daily_return)}>{signedPct(state.daily_return)}</b>
              </div>
              <div className="carry-metric">
                <span>Yıllık carry (30g)</span>
                <b className={tone(edge)}>{edge != null ? signedPct(edge) : "veri birikiyor"}</b>
              </div>
              <div className="carry-metric">
                <span>Sonraki dengeleme</span>
                <b>{data?.next_rebalance || "—"}</b>
              </div>
            </div>

            <div className="carry-hero-actions">
              <button onClick={step} disabled={stepping}>
                {stepping ? "Çalışıyor…" : "Günlük adımı çalıştır"}
              </button>
              <button className="mini-btn" onClick={load} disabled={loading} title="Yenile">
                <IconRefresh width={13} height={13} />
              </button>
              <button className="ghost-btn" onClick={reset}>
                Sıfırla
              </button>
            </div>

            <details className="carry-howto">
              <summary>Nasıl çalışır?</summary>
              <p>
                7 günlük ortalama fonlaması en yüksek 8 coin seçilir (pozitif ve günlük %0,5 tavan
                altı), eşit ağırlıkla long spot + short perp kurulur; fiyat yönü riski yoktur ve
                getiri tamamen fonlamadan gelir. 3 günde bir yeniden dengelenir; hysteresis (2
                bps/gün) gereksiz alım-satımı önler. Maliyet varsayımı 10 bps/bacak.{" "}
                {state.rebalanced ? "Son adımda pozisyonlar yeniden dengelendi." : ""}
                {state.note ? ` ${state.note}.` : ""}
              </p>
            </details>
          </div>

          {points && (
            <div className="card">
              <div className="card-head">
                <h3>Getiri eğrisi</h3>
                <span className="muted">
                  {series[0]?.as_of} → {series[series.length - 1]?.as_of}
                </span>
              </div>
              <svg className="carry-spark" viewBox="0 0 100 32" preserveAspectRatio="none">
                <polyline points={points} />
              </svg>
            </div>
          )}

          <div className="card">
            <div className="card-head">
              <h3>Pozisyonlar</h3>
              <span className="muted">Eşit ağırlık · {holdings.length} pozisyon</span>
            </div>
            <div className="table-wrap carry-table-wrap">
              <table className="compare-table carry-table">
                <thead>
                  <tr>
                    <th>Coin</th>
                    <th className="num">7g ortalama fonlama (günlük)</th>
                  </tr>
                </thead>
                <tbody>
                  {holdings.map((holding) => (
                    <tr key={holding.symbol}>
                      <td className="compare-symbol">{holding.symbol}</td>
                      <td className="num up">{fundingPct(holding.avg_funding)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <details className="card carry-collapse">
            <summary>
              Fonlama sıralaması · ilk 15 <span className="muted">(✓ pozisyonda)</span>
            </summary>
            <div className="table-wrap carry-table-wrap">
              <table className="compare-table carry-table">
                <thead>
                  <tr>
                    <th className="num">#</th>
                    <th>Coin</th>
                    <th className="num">7g ortalama fonlama</th>
                    <th className="num">Veri günü</th>
                    <th className="num">Pozisyon</th>
                  </tr>
                </thead>
                <tbody>
                  {ranking.slice(0, 15).map((row, index) => (
                    <tr key={row.symbol}>
                      <td className="num muted">{index + 1}</td>
                      <td className="compare-symbol">{row.symbol}</td>
                      <td className={`num ${row.avg_funding >= 0 ? "up" : "down"}`}>
                        {fundingPct(row.avg_funding)}
                      </td>
                      <td className="num muted">{row.days}</td>
                      <td className="num">{row.selected ? "✓" : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </div>
  );
}
