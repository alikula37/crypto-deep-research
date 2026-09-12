import { useEffect, useState } from "react";
import CoinSelect from "./CoinSelect.jsx";
import { api } from "./api.js";
import { DASH, formatDateTime, pct, price, priceRange, score as fmtScore } from "./format.js";
import { IconAlert, IconX } from "./icons.jsx";

const MAX_COINS = 4;

function ScoreBar({ value }) {
  if (value === null || value === undefined) return <span className="muted">{DASH}</span>;
  const width = Math.min(50, Math.abs(value) * 50);
  return (
    <span className="score-bar">
      <i
        className={value >= 0 ? "bar-up" : "bar-down"}
        style={{ width: `${width}%`, [value >= 0 ? "left" : "right"]: "50%" }}
      />
      <b>{fmtScore(value)}</b>
    </span>
  );
}

export default function ComparePanel({ initialCoin }) {
  const [coinIds, setCoinIds] = useState(initialCoin ? [initialCoin] : []);
  const [rows, setRows] = useState({});
  const [loading, setLoading] = useState(false);

  const load = (ids) => {
    if (!ids.length) {
      setRows({});
      return;
    }
    setLoading(true);
    setRows(Object.fromEntries(ids.map((id) => [id, { loading: true }])));
    Promise.all(
      ids.map(async (id) => {
        try {
          const [snapshot, runs] = await Promise.all([api.snapshot(id), api.runs(id)]);
          return [id, { snapshot, run: runs[runs.length - 1] || null }];
        } catch (err) {
          return [id, { error: err.message }];
        }
      })
    ).then((entries) => {
      setRows(Object.fromEntries(entries));
      setLoading(false);
    });
  };

  useEffect(() => {
    if (initialCoin) load([initialCoin]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const addCoin = (coin) => {
    if (!coin?.id) return;
    if (coinIds.includes(coin.id) || coinIds.length >= MAX_COINS) return;
    const next = [...coinIds, coin.id];
    setCoinIds(next);
    load(next);
  };

  const removeCoin = (id) => {
    const next = coinIds.filter((value) => value !== id);
    setCoinIds(next);
    load(next);
  };

  return (
    <div>
      <div className="toolbar compare-toolbar">
        <CoinSelect
          placeholder={coinIds.length ? "Coin ekle…" : "Karşılaştırmak için coin seçin…"}
          onSelect={addCoin}
          onSubmit={(value) => {
            const token = value.trim().toLowerCase();
            if (token) addCoin({ id: token });
          }}
        />
        <span className="muted">
          {coinIds.length}/{MAX_COINS} varlık — eklemek için listeden seçin
        </span>
        {loading && <span className="muted">Veriler getiriliyor…</span>}
      </div>

      {coinIds.length === 0 && (
        <div className="card compare-empty">
          <h3>Karşılaştırma için varlık ekleyin</h3>
          <p className="muted">
            En fazla {MAX_COINS} varlığı fiyat, 24s/7g/30g değişim, son skor ve olasılıkla yan yana
            kıyaslayabilirsiniz.
          </p>
        </div>
      )}

      {coinIds.length > 0 && (
        <div className="table-wrap">
          <table className="compare-table">
            <thead>
              <tr>
                <th>Varlık</th>
                <th>Fiyat</th>
                <th>24s</th>
                <th>7g</th>
                <th>30g</th>
                <th>Son Skor</th>
                <th>Yükseliş</th>
                <th>Beklenen Aralık</th>
                <th>Son Koşu</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {coinIds.map((id) => {
                const row = rows[id] || {};
                if (row.error) {
                  return (
                    <tr key={id}>
                      <td className="compare-symbol">{id}</td>
                      <td colSpan={8}>
                        <span className="error-inline">
                          <IconAlert width={13} height={13} /> {row.error}
                        </span>
                      </td>
                      <td>
                        <button className="mini-btn" onClick={() => removeCoin(id)}>
                          <IconX width={12} height={12} />
                        </button>
                      </td>
                    </tr>
                  );
                }
                const snapshot = row.snapshot?.snapshot;
                const run = row.run;
                return (
                  <tr key={id} className={row.loading ? "is-loading" : ""}>
                    <td className="compare-symbol">
                      {snapshot ? `${snapshot.coin.symbol.toUpperCase()} · ${snapshot.coin.name}` : id}
                    </td>
                    <td>{snapshot ? price(snapshot.price_usd) : DASH}</td>
                    <td className={(snapshot?.change_24h_pct ?? 0) >= 0 ? "up" : "down"}>
                      {pct(snapshot?.change_24h_pct, { signed: true })}
                    </td>
                    <td className={(snapshot?.change_7d_pct ?? 0) >= 0 ? "up" : "down"}>
                      {pct(snapshot?.change_7d_pct, { signed: true })}
                    </td>
                    <td className={(snapshot?.change_30d_pct ?? 0) >= 0 ? "up" : "down"}>
                      {pct(snapshot?.change_30d_pct, { signed: true })}
                    </td>
                    <td><ScoreBar value={run?.weighted_score} /></td>
                    <td>{run?.up_probability != null ? `%${Number(run.up_probability).toFixed(1)}` : DASH}</td>
                    <td>{run ? priceRange(run.expected_low, run.expected_high) : DASH}</td>
                    <td className="muted">
                      {run ? formatDateTime(run.created_at * 1000) : "koşu yok"}
                    </td>
                    <td>
                      <button className="mini-btn" onClick={() => removeCoin(id)} aria-label="Kaldır">
                        <IconX width={12} height={12} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
