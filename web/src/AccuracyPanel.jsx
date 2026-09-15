import { useEffect, useState } from "react";
import { api } from "./api.js";
import { DASH, formatDateTime, money, pct, score as fmtScore } from "./format.js";
import { IconRefresh, IconTarget } from "./icons.jsx";

const HORIZON_ORDER = ["1", "7", "30"];
const HORIZON_LABELS = { "1": "1 gün", "7": "7 gün", "30": "30 gün" };

function HitBadge({ hit }) {
  if (hit === null || hit === undefined) return <span className="muted">{DASH}</span>;
  return hit ? (
    <span className="hit-badge hit-true" title="Yön tuttu">✓</span>
  ) : (
    <span className="hit-badge hit-false" title="Yön tutmadı">✗</span>
  );
}

function ReturnCell({ value }) {
  if (value === null || value === undefined) return <span className="muted">{DASH}</span>;
  return <span className={value >= 0 ? "up" : "down"}>{pct(value, { signed: true })}</span>;
}

export default function AccuracyPanel({ coin }) {
  const [data, setData] = useState(null);
  const [calibration, setCalibration] = useState(null);
  const [models, setModels] = useState([]);
  const [drift, setDrift] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = () => {
    setLoading(true);
    setError("");
    api
      .accuracy(coin)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
    api
      .calibration(7, coin)
      .then(setCalibration)
      .catch(() => setCalibration(null));
    api
      .models()
      .then(setModels)
      .catch(() => setModels([]));
    api
      .learningStatus()
      .then((status) => setDrift(status?.drift || null))
      .catch(() => setDrift(null));
  };

  useEffect(load, [coin]);

  if (error) {
    return (
      <div className="error">
        <IconTarget width={15} height={15} /> {error}
      </div>
    );
  }
  if (!data) {
    return <div className="card skeleton-card"><div className="skeleton-line" /><div className="skeleton-line" /></div>;
  }

  const horizons = data.horizons || {};
  const runs = data.runs || [];
  const evaluated = Math.max(0, ...HORIZON_ORDER.map((key) => horizons[key]?.evaluated || 0));
  const directional = Math.max(0, ...HORIZON_ORDER.map((key) => horizons[key]?.directional || 0));

  return (
    <div>
      <div className="toolbar">
        <button onClick={load} disabled={loading}>
          <IconRefresh width={14} height={14} /> Yenile
        </button>
        <span className="muted">
          {runs.length} koşu · {evaluated} vadesi dolmuş değerlendirme
        </span>
      </div>

      {evaluated === 0 && (
        <div className="card accuracy-empty-note">
          <h3>Henüz vadesi dolmuş koşu yok</h3>
          <p className="muted">
            İsabet oranı için koşunun üzerinden en az 1/7/30 gün geçmesi gerekir. Koşular biriktikçe
            bu pano otomatik dolar; geçmiş tarihli koşular varsa getiriler anında hesaplanır.
          </p>
        </div>
      )}

      {calibration && (
        <div className="card calibration-strip">
          <div className="card-head">
            <h3>Kalibrasyon (7 gün)</h3>
            <span className={`status-badge tone-${calibration.n >= 100 ? "ok" : "muted"}`}>
              {calibration.n >= 100 ? "Örneklem yeterli" : `Heuristik · n=${calibration.n}`}
            </span>
          </div>
          <p className="muted small">
            {calibration.n === 0
              ? "Doldurulmuş sonuç etiketi yok; olasılıklar şimdilik kalibre edilmemiş heuristik değerlerdir."
              : `Brier ${calibration.brier ?? "—"} (temel ${calibration.baseline_brier ?? "—"}) · ECE ${
                  calibration.ece ?? "—"
                } · AUC ${calibration.auc ?? "—"} · yönlü gözlem ${calibration.directional ?? 0}`}
          </p>
          <details className="card-more">
            <summary>Model ve drift detayı</summary>
            {models.length > 0 &&
            (() => {
              let metrics = {};
              try {
                metrics = JSON.parse(models[0].metrics || "{}");
              } catch {
                metrics = {};
              }
              const hasOos = metrics.auc !== null && metrics.auc !== undefined;
              return (
                <p className="muted small">
                  Model: <b>{models[0].status === "active" ? "aktif" : "shadow"}</b> ·{" "}
                  {models[0].model_id} · n={models[0].train_rows} ·{" "}
                  {hasOos
                    ? `AUC ${metrics.auc} · Brier ${metrics.brier} (temel ${metrics.baseline_brier}) · ECE ${metrics.ece} · ${metrics.n_oos} OOS örnek`
                    : "OOS metrik yok (pencere için yetersiz örnek)"}
                </p>
              );
            })()}
          {drift && (
            <p className="muted small">
              Drift: {drift.alarm_count ? `${drift.alarm_count} alarm` : "temiz"} ·{" "}
              {(drift.metrics || []).map((metric) => {
                const value = metric.value === null || metric.value === undefined ? "—" : metric.value;
                return `${metric.metric}=${value}${metric.alarm ? " ⚠" : ""}`;
              }).join(" · ") || "henüz ölçüm yok"}
            </p>
          )}
          </details>
          {calibration.n >= 100 && calibration.bins?.length > 0 && (
            <div className="table-wrap">
              <table className="accuracy-table">
                <thead>
                  <tr>
                    <th>Olasılık aralığı</th>
                    <th>Gözlem</th>
                    <th>Tahmin</th>
                    <th>Gözlenen</th>
                    <th>%95 GA</th>
                  </tr>
                </thead>
                <tbody>
                  {calibration.bins.map((bin) => (
                    <tr key={bin.bin_index}>
                      <td>
                        %{(bin.bin_low * 100).toFixed(0)}–{(bin.bin_high * 100).toFixed(0)}
                      </td>
                      <td>{bin.n}</td>
                      <td>%{(bin.predicted_mean * 100).toFixed(1)}</td>
                      <td>%{(bin.observed_rate * 100).toFixed(1)}</td>
                      <td className="muted">
                        %{((bin.ci_low ?? 0) * 100).toFixed(0)}–{((bin.ci_high ?? 0) * 100).toFixed(0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <div className="accuracy-grid">
        {HORIZON_ORDER.map((key) => {
          const stats = horizons[key] || {};
          const rate = stats.hit_rate;
          return (
            <div className="card accuracy-card" key={key}>
              <div className="accuracy-head">
                <h3>{HORIZON_LABELS[key]}</h3>
                <span className="muted">
                  {stats.directional || 0} yönlü / {stats.evaluated || 0} değerlendirme
                </span>
              </div>
              <div className={`accuracy-rate ${rate === null || rate === undefined ? "muted" : rate >= 0.5 ? "up" : "down"}`}>
                {rate === null || rate === undefined ? DASH : `%${(rate * 100).toFixed(0)}`}
                <span className="accuracy-rate-label">isabet</span>
              </div>
              <div className="accuracy-rows">
                <div>
                  <span className="muted">Yükseliş sinyali ort. getiri</span>
                  <ReturnCell value={stats.avg_return_positive_signals_pct} />
                </div>
                <div>
                  <span className="muted">Düşüş sinyali ort. getiri</span>
                  <ReturnCell value={stats.avg_return_negative_signals_pct} />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="table-wrap">
        <table className="accuracy-table">
          <thead>
            <tr>
              <th>Tarih</th>
              <th>Coin</th>
              <th>Skor</th>
              <th>Giriş</th>
              <th>1 gün</th>
              <th>7 gün</th>
              <th>30 gün</th>
              <th>İsabet (7g)</th>
              <th>İsabet (30g)</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.run_id}>
                <td>{formatDateTime(run.created_at * 1000)}</td>
                <td className="accuracy-symbol">{run.symbol || run.coin}</td>
                <td>
                  <span className={(run.weighted_score ?? 0) >= 0 ? "up" : "down"}>
                    {fmtScore(run.weighted_score)}
                  </span>
                </td>
                <td>{money(run.current_price, { exact: true })}</td>
                <td><ReturnCell value={run.returns_pct?.["1"]} /></td>
                <td><ReturnCell value={run.returns_pct?.["7"]} /></td>
                <td><ReturnCell value={run.returns_pct?.["30"]} /></td>
                <td><HitBadge hit={run.hits?.["7"]} /></td>
                <td><HitBadge hit={run.hits?.["30"]} /></td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr>
                <td colSpan={9} className="muted">Kayıtlı koşu yok.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {data.note && <p className="muted small">{data.note}</p>}
    </div>
  );
}
