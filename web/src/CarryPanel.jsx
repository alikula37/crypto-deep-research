import { useEffect, useState } from "react";
import { api } from "./api.js";
import { IconRefresh } from "./icons.jsx";

function signedPct(value) {
  if (value === null || value === undefined) return "—";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
}

function fundingPct(value) {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(4)}%`;
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
    if (!window.confirm("Paper takip durumu sıfırlanacak. Emin misiniz?")) return;
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
  const params = state?.params || data?.defaults || {};
  const heldSymbols = new Set(holdings.map((holding) => holding.symbol));

  return (
    <div>
      {error && <div className="error">{error}</div>}

      <div className="card">
        <div className="card-head">
          <h3>Fonlama Carry · Paper Takip</h3>
          <div className="alarm-form">
            <button onClick={step} disabled={stepping}>
              {stepping ? "Çalışıyor…" : "Günlük adımı çalıştır"}
            </button>
            <button className="mini-btn" onClick={reset} title="Paper durumunu sıfırla">
              Sıfırla
            </button>
            <button className="mini-btn" onClick={load} disabled={loading} title="Yenile">
              <IconRefresh width={13} height={13} />
            </button>
          </div>
        </div>
        <p className="muted carry-note">
          Long spot + short perp (delta-nötr): getiri = toplanan fonlama − işlem maliyeti, fiyat
          yönü riski yoktur. Sinyal: 7g ortalama fonlaması en yüksek {params.top_n || 8} coin
          ({params.universe || 40} perp evren, yalnız pozitif fonlamalılar),{" "}
          {params.rebalance_days || 7} günde bir yeniden dengeleme. Maliyet varsayımı{" "}
          {params.cost_bps || 6} bps/bacak.
        </p>
        <p className="muted">
          {state
            ? `Son güncelleme: ${state.as_of}${state.rebalanced ? " · yeniden dengelendi" : ""} · sonraki rebalance: ${data?.next_rebalance || "—"}`
            : "Paper takip henüz başlamadı: Günlük adımı çalıştır ile başlatın."}
        </p>
      </div>

      {state && (
        <div className="portfolio-totals">
          <div className="card portfolio-total">
            <span className="muted">Equity (×)</span>
            <b>{state.equity.toFixed(4)}</b>
          </div>
          <div className="card portfolio-total">
            <span className="muted">Günlük</span>
            <b className={state.daily_return >= 0 ? "up" : "down"}>
              {signedPct(state.daily_return)}
            </b>
          </div>
          <div className="card portfolio-total">
            <span className="muted">Kümülatif</span>
            <b className={state.equity >= 1 ? "up" : "down"}>{signedPct(state.equity - 1)}</b>
          </div>
          <div className="card portfolio-total">
            <span className="muted">Bugünkü fonlama geliri</span>
            <b className={state.funding_income >= 0 ? "up" : "down"}>
              {signedPct(state.funding_income)}
            </b>
          </div>
          <div className="card portfolio-total">
            <span className="muted">Takip günü</span>
            <b>{series.length}</b>
          </div>
        </div>
      )}

      {points && (
        <div className="card">
          <div className="card-head">
            <h3>Equity Eğrisi</h3>
            <span className="muted">
              {series[0]?.as_of} → {series[series.length - 1]?.as_of}
            </span>
          </div>
          <svg className="carry-spark" viewBox="0 0 100 32" preserveAspectRatio="none">
            <polyline points={points} />
          </svg>
        </div>
      )}

      {!state ? (
        <div className="card compare-empty">
          <h3>Paper takip bekleniyor</h3>
          <p className="muted">
            5,5 yıllık testte bu kurulum %9,6/yıl getiri, Sharpe 4,35, maksimum %-4 düşüş üretti
            (kaldıraçsız). Paper takip canlı fonlama verisiyle günlük olarak ilerler.
          </p>
        </div>
      ) : (
        <>
          <div className="card">
            <div className="card-head">
              <h3>Pozisyonlar</h3>
              <span className="muted">
                Eşit ağırlık · toplam {holdings.length} pozisyon
              </span>
            </div>
            <div className="table-wrap">
              <table className="compare-table">
                <thead>
                  <tr>
                    <th>Coin</th>
                    <th>Ağırlık</th>
                    <th>7g ortalama fonlama (günlük)</th>
                    <th>Günlük katkı tahmini</th>
                  </tr>
                </thead>
                <tbody>
                  {holdings.map((holding) => (
                    <tr key={holding.symbol}>
                      <td className="compare-symbol">{holding.symbol}</td>
                      <td>{fundingPct(holding.weight)}</td>
                      <td className="up">{fundingPct(holding.avg_funding)}</td>
                      <td>{signedPct((holding.avg_funding || 0) * holding.weight)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <div className="card-head">
              <h3>Fonlama Sıralaması</h3>
              <span className="muted">En yüksek 7g ortalama fonlama · ✓ işaretliler pozisyonda</span>
            </div>
            <div className="table-wrap">
              <table className="compare-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Coin</th>
                    <th>7g ortalama fonlama</th>
                    <th>Veri günü</th>
                    <th>Pozisyon</th>
                  </tr>
                </thead>
                <tbody>
                  {ranking.slice(0, 15).map((row, index) => (
                    <tr key={row.symbol}>
                      <td className="muted">{index + 1}</td>
                      <td className="compare-symbol">{row.symbol}</td>
                      <td className={row.avg_funding >= 0 ? "up" : "down"}>
                        {fundingPct(row.avg_funding)}
                      </td>
                      <td className="muted">{row.days}</td>
                      <td>{heldSymbols.has(row.symbol) ? "✓" : row.selected ? "seçili" : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
