"""Carry paper takip testleri: siralama, adim uygulama, idempotans, maliyet."""

from datetime import date, timedelta

from crypto_deep_research.learning.carry import (
    apply_step,
    next_rebalance_date,
    rank_funding,
)
from crypto_deep_research.learning.strategies import select_holdings

PARAMS = {
    "universe": 40,
    "top_n": 2,
    "lookback": 3,
    "rebalance_days": 7,
    "cost_bps": 6.0,
    "min_avg": 0.0,
}


def _funding(rates: dict[str, float], days: int = 10) -> dict[str, dict[str, float]]:
    base = date(2025, 1, 1)
    return {
        symbol: {(base + timedelta(days=index)).isoformat(): rate for index in range(days)}
        for symbol, rate in rates.items()
    }


def test_rank_funding_selects_highest_and_filters_negative():
    funding = _funding({"AAAUSDT": 0.001, "BBBUSDT": 0.0005, "CCCUSDT": -0.002})
    ranked = rank_funding(funding, top_n=2, lookback=3, min_avg=0.0)
    assert [row["symbol"] for row in ranked[:2]] == ["AAAUSDT", "BBBUSDT"]
    assert ranked[0]["selected"] and ranked[1]["selected"]
    assert not ranked[2]["selected"]
    assert ranked[0]["days"] == 3


def test_apply_step_opens_positions_with_cost():
    funding = _funding({"AAAUSDT": 0.001, "BBBUSDT": 0.0005, "CCCUSDT": -0.002})
    state = apply_step(None, funding, PARAMS, "2025-01-10")
    assert state["rebalanced"] is True
    assert state["last_rebalance"] == "2025-01-10"
    assert len(state["holdings"]) == 2
    assert abs(state["holdings"][0]["weight"] - 0.5) < 1e-9
    expected_cost = 6.0 * 2 / 10_000
    assert abs(state["equity"] - (1 - expected_cost)) < 1e-9
    assert state["note"] == "acilis"


def test_apply_step_same_day_is_idempotent():
    funding = _funding({"AAAUSDT": 0.001, "BBBUSDT": 0.0005})
    state = apply_step(None, funding, PARAMS, "2025-01-10")
    again = apply_step(state, funding, PARAMS, "2025-01-10")
    assert again is state


def test_apply_step_accrues_funding_income():
    funding = _funding({"AAAUSDT": 0.001, "BBBUSDT": 0.0005})
    state = apply_step(None, funding, PARAMS, "2025-01-09")
    state["last_rebalance"] = "2025-01-05"
    funding = _funding({"AAAUSDT": 0.002, "BBBUSDT": 0.001})
    stepped = apply_step(state, funding, PARAMS, "2025-01-10")
    expected_income = 0.5 * 0.002 + 0.5 * 0.001
    assert abs(stepped["funding_income"] - expected_income) < 1e-9
    assert stepped["costs"] == 0.0
    assert stepped["rebalanced"] is False
    assert abs(stepped["equity"] - state["equity"] * (1 + expected_income)) < 1e-9


def test_apply_step_rebalances_and_charges_turnover():
    funding = _funding({"AAAUSDT": 0.001, "BBBUSDT": 0.0009, "CCCUSDT": 0.0005})
    state = apply_step(None, funding, PARAMS, "2025-01-09")
    state["last_rebalance"] = "2025-01-01"
    funding = _funding({"AAAUSDT": 0.003, "BBBUSDT": 0.0001, "CCCUSDT": 0.002})
    stepped = apply_step(state, funding, PARAMS, "2025-01-10")
    assert stepped["rebalanced"] is True
    symbols = {holding["symbol"] for holding in stepped["holdings"]}
    assert symbols == {"AAAUSDT", "CCCUSDT"}
    expected_turnover = 1.0  # yarim portfoy degisti: BBB cikti, CCC girdi
    expected_cost = expected_turnover * 6.0 * 2 / 10_000
    assert abs(stepped["costs"] - expected_cost) < 1e-9


def test_next_rebalance_date():
    state = {"as_of": "2025-01-10", "last_rebalance": "2025-01-08", "params": PARAMS}
    assert next_rebalance_date(state) == "2025-01-15"
    assert next_rebalance_date(None) is None


def test_rank_funding_respects_max_avg_cap():
    funding = _funding({"AAAUSDT": 0.02, "BBBUSDT": 0.001, "CCCUSDT": 0.0005})
    ranked = rank_funding(funding, top_n=2, lookback=3, min_avg=0.0, max_avg=0.005)
    selected = [row["symbol"] for row in ranked if row["selected"]]
    assert selected == ["BBBUSDT", "CCCUSDT"]
    assert ranked[0]["symbol"] == "AAAUSDT" and not ranked[0]["selected"]


def test_select_holdings_equal_and_cap():
    history = {"A": 0.002, "B": 0.001, "C": 0.0005, "D": 0.02}
    weights = select_holdings(history, top_n=3, max_avg=0.005)
    assert set(weights) == {"A", "B", "C"}
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert all(abs(value - 1 / 3) < 1e-9 for value in weights.values())


def test_select_holdings_hysteresis_keeps_incumbent():
    history = {"OLD": 0.0010, "NEW": 0.0011}
    without = select_holdings(history, top_n=1)
    assert set(without) == {"NEW"}
    with_hyst = select_holdings(history, top_n=1, incumbents={"OLD"}, hysteresis=0.0002)
    assert set(with_hyst) == {"OLD"}


def test_select_holdings_funding_weighting_is_capped():
    history = {"A": 0.004, "B": 0.001, "C": 0.001}
    weights = select_holdings(history, top_n=3, weighting="funding", max_weight=0.5)
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    assert max(weights.values()) <= 0.5 + 1e-9
    assert weights["A"] > weights["B"]


def test_status_computes_edge_health():
    class _Db:
        def carry_state_latest(self):
            return {"as_of": "2025-02-01"}

        def carry_state_series(self, limit=365):
            return [
                {"as_of": f"2025-01-{day:02d}", "funding_income": 0.0004, "daily_return": 0.0003}
                for day in range(1, 31)
            ]

    from crypto_deep_research.learning.carry import status

    snapshot = status(_Db())
    assert snapshot["state"]["as_of"] == "2025-02-01"
    assert abs(snapshot["edge_30d_annual"] - 0.0004 * 365) < 1e-9
    assert abs(snapshot["net_30d_annual"] - 0.0003 * 365) < 1e-9


def test_edge_alert_severities():
    from crypto_deep_research.learning.carry import edge_alert

    assert edge_alert({"net_30d_annual": 0.05}) is None
    warning = edge_alert({"net_30d_annual": 0.02})
    assert warning is not None and warning["severity"] == "warning"
    critical = edge_alert({"net_30d_annual": 0.005})
    assert critical is not None and critical["severity"] == "critical"
    assert edge_alert({"net_30d_annual": None, "edge_30d_annual": None}) is None
    fallback = edge_alert({"net_30d_annual": None, "edge_30d_annual": 0.02})
    assert fallback is not None and fallback["severity"] == "warning"
