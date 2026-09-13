import { useEffect, useState } from "react";
import CoinSelect from "./CoinSelect.jsx";
import { api } from "./api.js";
import { DASH, money, pct, price } from "./format.js";
import { IconCheck, IconEdit, IconRefresh, IconX } from "./icons.jsx";

function pnlClass(value) {
  if (value === null || value === undefined) return "muted";
  return value >= 0 ? "up" : "down";
}

function signedMoney(value) {
  if (value === null || value === undefined) return DASH;
  return `${value >= 0 ? "+" : "-"}${money(Math.abs(value), { exact: true })}`;
}

export default function PortfolioPanel({ initialCoin }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ coin: initialCoin || "", amount: "", entry_price: "", note: "" });
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({ amount: "", entry_price: "", note: "" });

  const load = () => {
    setLoading(true);
    api
      .portfolio()
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const add = async () => {
    const amount = Number(form.amount);
    const entryPrice = Number(form.entry_price);
    if (!form.coin || Number.isNaN(amount) || amount <= 0 || Number.isNaN(entryPrice) || entryPrice <= 0) {
      setError("Coin, miktar ve giriş fiyatı zorunludur (pozitif sayı).");
      return;
    }
    setError("");
    try {
      await api.portfolioAdd({
        coin: form.coin,
        amount,
        entry_price: entryPrice,
        note: form.note || null,
      });
      setForm({ coin: form.coin, amount: "", entry_price: "", note: "" });
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const remove = async (id) => {
    try {
      await api.portfolioRemove(id);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const startEdit = (position) => {
    setEditingId(position.id);
    setEditForm({
      amount: String(position.amount),
      entry_price: String(position.entry_price),
      note: position.note || "",
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm({ amount: "", entry_price: "", note: "" });
  };

  const saveEdit = async (id) => {
    const amount = Number(editForm.amount);
    const entryPrice = Number(editForm.entry_price);
    if (Number.isNaN(amount) || amount <= 0 || Number.isNaN(entryPrice) || entryPrice <= 0) {
      setError("Miktar ve giriş fiyatı pozitif sayı olmalıdır.");
      return;
    }
    setError("");
    try {
      await api.portfolioUpdate(id, {
        amount,
        entry_price: entryPrice,
        note: editForm.note || null,
      });
      cancelEdit();
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const totals = data?.totals;
  const positions = data?.positions || [];

  return (
    <div>
      {error && <div className="error">{error}</div>}

      <div className="card portfolio-form-card">
        <div className="card-head">
          <h3>Pozisyon Ekle</h3>
          <span className="muted">Miktar coin cinsindendir; giriş fiyatı USD.</span>
        </div>
        <div className="alarm-form">
          <CoinSelect
            defaultValue={form.coin}
            placeholder="Coin seçin…"
            onManualChange={(value) => setForm((prev) => ({ ...prev, coin: value.trim().toLowerCase() }))}
            onSelect={(coin) => setForm((prev) => ({ ...prev, coin: coin.id }))}
          />
          <input
            type="number"
            step="any"
            placeholder="Miktar"
            value={form.amount}
            onChange={(event) => setForm((prev) => ({ ...prev, amount: event.target.value }))}
          />
          <input
            type="number"
            step="any"
            placeholder="Giriş fiyatı ($)"
            value={form.entry_price}
            onChange={(event) => setForm((prev) => ({ ...prev, entry_price: event.target.value }))}
          />
          <input
            type="text"
            placeholder="Not (opsiyonel)"
            value={form.note}
            onChange={(event) => setForm((prev) => ({ ...prev, note: event.target.value }))}
            onKeyDown={(event) => event.key === "Enter" && add()}
          />
          <button onClick={add}>Ekle</button>
          <button className="mini-btn" onClick={load} disabled={loading} title="Yenile">
            <IconRefresh width={13} height={13} />
          </button>
        </div>
      </div>

      {totals && (
        <div className="portfolio-totals">
          <div className="card portfolio-total">
            <span className="muted">Toplam Değer</span>
            <b>{money(totals.value_usd, { exact: true })}</b>
          </div>
          <div className="card portfolio-total">
            <span className="muted">Toplam Maliyet</span>
            <b>{money(totals.cost_usd, { exact: true })}</b>
          </div>
          <div className="card portfolio-total">
            <span className="muted">Kâr / Zarar</span>
            <b className={pnlClass(totals.pnl_usd)}>
              {signedMoney(totals.pnl_usd)} {totals.pnl_pct != null ? `(${pct(totals.pnl_pct, { signed: true })})` : ""}
            </b>
          </div>
          <div className="card portfolio-total">
            <span className="muted">Pozisyon</span>
            <b>{totals.positions}</b>
          </div>
        </div>
      )}

      {positions.length === 0 ? (
        <div className="card compare-empty">
          <h3>Portföy boş</h3>
          <p className="muted">
            Elde tuttuğunuz coinleri miktar ve giriş fiyatıyla ekleyin; değer ve kâr/zarar canlı
            fiyatlarla hesaplanır.
          </p>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="compare-table">
            <thead>
              <tr>
                <th>Varlık</th>
                <th>Miktar</th>
                <th>Giriş</th>
                <th>Güncel</th>
                <th>Değer</th>
                <th>Kâr / Zarar</th>
                <th>Pay</th>
                <th>Not</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {positions.map((position) => (
                <tr key={position.id}>
                  <td className="compare-symbol">
                    {position.symbol || position.coin}
                    <span className="muted small"> {position.name || ""}</span>
                  </td>
                  {editingId === position.id ? (
                    <>
                      <td>
                        <input
                          className="inline-input"
                          type="number"
                          step="any"
                          value={editForm.amount}
                          onChange={(event) => setEditForm((prev) => ({ ...prev, amount: event.target.value }))}
                        />
                      </td>
                      <td>
                        <input
                          className="inline-input"
                          type="number"
                          step="any"
                          value={editForm.entry_price}
                          onChange={(event) => setEditForm((prev) => ({ ...prev, entry_price: event.target.value }))}
                        />
                      </td>
                      <td>{position.current_price != null ? price(position.current_price) : DASH}</td>
                      <td>{position.value_usd != null ? money(position.value_usd, { exact: true }) : DASH}</td>
                      <td className={pnlClass(position.pnl_usd)}>
                        {position.pnl_usd != null
                          ? `${signedMoney(position.pnl_usd)} (${pct(position.pnl_pct, { signed: true })})`
                          : DASH}
                      </td>
                      <td>
                        {position.allocation_pct != null ? `%${position.allocation_pct.toFixed(1)}` : DASH}
                      </td>
                      <td>
                        <input
                          className="inline-input"
                          type="text"
                          placeholder="Not"
                          value={editForm.note}
                          onChange={(event) => setEditForm((prev) => ({ ...prev, note: event.target.value }))}
                          onKeyDown={(event) => event.key === "Enter" && saveEdit(position.id)}
                        />
                      </td>
                      <td className="inline-actions">
                        <button
                          className="mini-btn"
                          onClick={() => saveEdit(position.id)}
                          title="Kaydet"
                        >
                          <IconCheck width={12} height={12} />
                        </button>
                        <button className="mini-btn" onClick={cancelEdit} title="Vazgeç">
                          <IconX width={12} height={12} />
                        </button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td>{position.amount}</td>
                      <td>{price(position.entry_price)}</td>
                      <td>{position.current_price != null ? price(position.current_price) : DASH}</td>
                      <td>{position.value_usd != null ? money(position.value_usd, { exact: true }) : DASH}</td>
                      <td className={pnlClass(position.pnl_usd)}>
                        {position.pnl_usd != null
                          ? `${signedMoney(position.pnl_usd)} (${pct(position.pnl_pct, { signed: true })})`
                          : DASH}
                      </td>
                      <td>
                        {position.allocation_pct != null ? `%${position.allocation_pct.toFixed(1)}` : DASH}
                      </td>
                      <td className="muted">{position.note || ""}</td>
                      <td className="inline-actions">
                        <button
                          className="mini-btn"
                          onClick={() => startEdit(position)}
                          title="Düzenle"
                        >
                          <IconEdit width={12} height={12} />
                        </button>
                        <button className="mini-btn" onClick={() => remove(position.id)} title="Sil">
                          <IconX width={12} height={12} />
                        </button>
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
