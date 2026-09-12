"""Borsa saglayici yardimcilari: 1000x perpetual sembolleri ve carpanlar."""

from crypto_deep_research.providers.exchange import ExchangeProvider


class _Dummy:
    pass


def _provider() -> ExchangeProvider:
    return ExchangeProvider(http=_Dummy(), settings=_Dummy())


def test_perp_symbol_overrides():
    provider = _provider()
    assert provider.perp_symbol("pepe") == "1000PEPEUSDT"
    assert provider.perp_symbol("SHIB") == "1000SHIBUSDT"
    assert provider.perp_symbol("btc") == "BTCUSDT"
    assert provider.perp_symbol("ETHUSDT") == "ETHUSDT"


def test_perp_multiplier():
    assert ExchangeProvider.perp_multiplier("1000PEPEUSDT") == 1000.0
    assert ExchangeProvider.perp_multiplier("BTCUSDT") == 1.0
    assert ExchangeProvider.perp_multiplier("1000BONKUSDT") == 1000.0


def test_mcp_exposes_price_chart_tool():
    import asyncio

    from crypto_deep_research import mcp_server

    tools = asyncio.run(mcp_server.server.list_tools())
    names = {tool.name for tool in tools}
    assert "get_price_chart" in names
    assert "deep_research" in names
