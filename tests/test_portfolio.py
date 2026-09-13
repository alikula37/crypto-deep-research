"""Portfoy degerleme testleri."""

from crypto_deep_research.portfolio import compute_portfolio


def _entry(position_id=1, coin="bitcoin", amount=0.5, entry_price=50000.0, symbol="BTC"):
    return {
        "id": position_id,
        "coin": coin,
        "symbol": symbol,
        "name": coin.title(),
        "amount": amount,
        "entry_price": entry_price,
        "note": None,
    }


def test_compute_portfolio_values_and_pnl():
    result = compute_portfolio(
        [_entry(), _entry(2, "ethereum", amount=10, entry_price=2000.0, symbol="ETH")],
        {"bitcoin": 60000.0, "ethereum": 1800.0},
    )
    btc, eth = result["positions"]
    assert btc["value_usd"] == 30000.0
    assert btc["pnl_usd"] == 5000.0
    assert btc["pnl_pct"] == 20.0
    assert eth["pnl_usd"] == -2000.0
    assert eth["pnl_pct"] == -10.0
    assert btc["allocation_pct"] == 62.5
    assert eth["allocation_pct"] == 37.5
    totals = result["totals"]
    assert totals["value_usd"] == 48000.0
    assert totals["cost_usd"] == 45000.0
    assert totals["pnl_usd"] == 3000.0


def test_missing_price_marks_position_unvalued():
    result = compute_portfolio([_entry()], {"bitcoin": None})
    position = result["positions"][0]
    assert position["value_usd"] is None
    assert position["pnl_usd"] is None
    assert position["allocation_pct"] is None
    assert result["totals"]["value_usd"] == 0.0
    assert result["totals"]["cost_usd"] == 25000.0


def test_empty_portfolio():
    result = compute_portfolio([], {})
    assert result["positions"] == []
    assert result["totals"]["positions"] == 0
    assert result["totals"]["pnl_pct"] is None
