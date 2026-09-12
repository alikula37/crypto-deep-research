"""Balina akışları analizi: büyük zincir-üstü transferler ve stablecoin likiditesi."""

from __future__ import annotations

from typing import Any

from crypto_deep_research.analysis.base import AnalysisContext, clamp
from crypto_deep_research.formatting import num, pct
from crypto_deep_research.models import AnalysisResult, WhaleFlow
from crypto_deep_research.providers.base import ProviderError, source

CHAIN_BY_COIN = {
    "bitcoin": "bitcoin",
    "ethereum": "ethereum",
}


async def analyze_whales(ctx: AnalysisContext) -> AnalysisResult:
    snapshot = await ctx.snapshot()
    chain = CHAIN_BY_COIN.get(ctx.coin.id)
    sources = [source("DefiLlama Stablecoins", "https://defillama.com/stablecoins", note="stablecoin likiditesi")]

    flows: list[WhaleFlow] = []
    warnings: list[str] = []
    if chain == "bitcoin":
        flows = await ctx.providers.onchain.btc_large_transactions(min_btc=50.0)
        sources.append(
            source("blockchain.com", "https://api.blockchain.info", note="mempool büyük BTC transferleri")
        )
    elif chain == "ethereum":
        flows = await ctx.providers.onchain.eth_large_transactions(min_eth=1000.0)
        sources.append(
            source("Blockscout", "https://eth.blockscout.com", note="son bloklar büyük ETH transferleri")
        )
    else:
        warnings.append(
            f"{ctx.coin.symbol.upper()} için ücretsiz büyük cüzdan akış verisi yok; "
            "stablecoin likiditesi ve haber verisi kullanıldı."
        )

    stablecoin_data: dict[str, Any] = {}
    try:
        charts = await ctx.providers.defillama.stablecoin_charts_all()
        if charts:
            latest = charts[-1].get("totalCirculatingUSD") or {}
            total_now = sum(float(v) for v in latest.values()) if isinstance(latest, dict) else float(latest)
            past = None
            if len(charts) > 7:
                past_map = charts[-8].get("totalCirculatingUSD") or {}
                past = sum(float(v) for v in past_map.values()) if isinstance(past_map, dict) else float(past_map)
            change_7d = (total_now / past - 1) * 100 if past else None
            stablecoin_data = {
                "stablecoin_total_usd": total_now,
                "stablecoin_change_7d_pct": round(change_7d, 2) if change_7d is not None else None,
            }
    except ProviderError:
        pass

    total_supply = snapshot.circulating_supply or snapshot.total_supply
    exchange_in = sum(flow.amount for flow in flows if flow.direction == "exchange_in")
    exchange_out = sum(flow.amount for flow in flows if flow.direction == "exchange_out")
    unknown = sum(flow.amount for flow in flows if flow.direction == "unknown")

    score = 0.0
    confidence = 0.0
    reasons: list[str] = []

    if flows:
        confidence += min(0.4, len(flows) / 50 * 0.4)
        if total_supply:
            data_in_ratio = exchange_in / total_supply * 100
            data_out_ratio = exchange_out / total_supply * 100
        else:
            data_in_ratio = data_out_ratio = None
        if exchange_out + exchange_in > 0:
            net = exchange_out - exchange_in
            net_ratio = net / (exchange_out + exchange_in)
            if net_ratio > 0.15:
                score += 0.5
                reasons.append("Borsalardan çıkış baskın: birikim sinyali (bullish)")
            elif net_ratio < -0.15:
                score -= 0.5
                reasons.append("Borsalara giriş baskın: satış baskısı sinyali (bearish)")
        elif unknown:
            reasons.append("Transfer yönü etiketlenemedi; hacim volatilite göstergesi olarak kullanıldı")
        whale_in = exchange_in or 0
        whale_out = exchange_out or 0
    else:
        data_in_ratio = data_out_ratio = whale_in = whale_out = None

    stable_change = stablecoin_data.get("stablecoin_change_7d_pct")
    if stable_change is not None:
        reasons.append(
            f"Stablecoin arzı 7 günde %{stable_change:+.2f} (bilgi amaçlı; akış skoru 62. maddede)"
        )

    if not flows:
        return ctx.result(
            "whales",
            "Balina Alım-Satım / Toplam Arz",
            status="partial",
            summary=(
                "Son bloklarda eşiği aşan büyük transfer bulunamadı; yön sinyali üretilemedi "
                "(bu, sıfır akış anlamına gelmez, örneklem sınırlıdır)."
            ),
            data={"flows_count": 0, "reasons": reasons, **stablecoin_data},
            sources=sources,
            score=None,
            confidence=0.0,
            warnings=[
                "Bu çalıştırmada balina yön sinyali yok; madde ağırlıklı ortalamaya dahil edilmedi."
            ],
        )

    top_flows = sorted(flows, key=lambda flow: flow.amount, reverse=True)[:10]
    if chain is None:
        summary_parts = [
            f"{ctx.coin.symbol.upper()} için zincir-üstü büyük cüzdan taraması mevcut değil "
            "(ücretsiz veri yalnızca BTC/ETH için sağlanıyor)."
        ]
        if stable_change is not None:
            summary_parts.append(f"Stablecoin arzı 7 günlük değişimi {pct(stable_change, signed=True)}.")
        summary = " ".join(summary_parts)
    else:
        summary = (
            f"{len(flows)} büyük transfer tarandı. Borsaya giriş {num(exchange_in, 4)} "
            f"{ctx.coin.symbol.upper()}, çıkış {num(exchange_out, 4)} {ctx.coin.symbol.upper()}."
        )
        if not flows:
            summary = (
                "Son bloklarda eşiği aşan büyük transfer bulunamadı "
                "(bu, sıfır akış anlamına gelmez; örneklem sınırlıdır)."
            )
        if stable_change is not None:
            summary += f" Stablecoin arzı 7 günlük değişimi {pct(stable_change, signed=True)}."

    return ctx.result(
        "whales",
        "Balina Alım-Satım / Toplam Arz",
        status="partial" if warnings else "ok",
        summary=summary,
        data={
            "flows_count": len(flows),
            "exchange_in_amount": whale_in,
            "exchange_out_amount": whale_out,
            "unknown_amount": unknown or None,
            "exchange_in_pct_supply": round(data_in_ratio, 4) if data_in_ratio else None,
            "exchange_out_pct_supply": round(data_out_ratio, 4) if data_out_ratio else None,
            "top_flows": [flow.model_dump(mode="json") for flow in top_flows],
            "reasons": reasons,
            **stablecoin_data,
        },
        sources=sources,
        score=round(clamp(score), 4),
        confidence=round(min(confidence, 1.0), 3),
        warnings=warnings,
    )
