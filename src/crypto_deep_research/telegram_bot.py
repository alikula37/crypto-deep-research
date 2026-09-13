"""Telegram botu: uzaktan fiyat, skor, rapor ve arastirma komutlari (opsiyonel).

Kullanim:
    uv run cdr telegram            # CDR_TELEGRAM_TOKEN ortam degiskeni ile
    uv run cdr telegram --token X  # acik token ile
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from crypto_deep_research.config import Settings, get_settings
from crypto_deep_research.deep_research.engine import DeepResearchEngine
from crypto_deep_research.formatting import money, pct, price, score
from crypto_deep_research.providers.registry import build_providers
from crypto_deep_research.storage.db import Database

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
MAX_MESSAGE = 4000

HELP_TEXT = (
    "Crypto Deep Research botu\n\n"
    "Komutlar:\n"
    "/fiyat <coin> — anlık fiyat, piyasa değeri ve 24s değişim\n"
    "/skor <coin> — en son derin araştırma skoru ve olasılıklar\n"
    "/rapor <coin> — en son raporun özeti\n"
    "/arastir <coin> [profil] — yeni derin araştırma başlatır (profil: dengeli|muhafazakar|agresif)\n"
    "/yardim — bu mesaj\n\n"
    "Örnek: /arastir bitcoin muhafazakar"
)

PROFILE_ALIASES = {
    "dengeli": "balanced",
    "balanced": "balanced",
    "muhafazakar": "conservative",
    "muhafazakâr": "conservative",
    "conservative": "conservative",
    "agresif": "aggressive",
    "aggressive": "aggressive",
}


def parse_command(text: str) -> tuple[str, list[str]]:
    """'/fiyat BTC' -> ('fiyat', ['BTC']); @bot eki ve fazla bosluklar temizlenir."""
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return "", []
    parts = raw.split()
    command = parts[0][1:].split("@")[0].lower()
    return command, parts[1:]


async def _call(client: httpx.AsyncClient, token: str, method: str, **payload: Any) -> dict:
    response = await client.post(f"{API_BASE}/bot{token}/{method}", json=payload)
    data = response.json()
    if not data.get("ok"):
        logger.warning("Telegram API hatasi (%s): %s", method, data.get("description"))
    return data


async def _send(client: httpx.AsyncClient, token: str, chat_id: int, text: str) -> None:
    chunks = [text[i : i + MAX_MESSAGE] for i in range(0, len(text), MAX_MESSAGE)] or [""]
    for chunk in chunks:
        await _call(client, token, "sendMessage", chat_id=chat_id, text=chunk)


async def _snapshot_reply(providers, settings: Settings, coin: str) -> str:
    ref = await providers.coingecko.resolve(coin)
    snapshot = await providers.coingecko.snapshot(ref)
    return (
        f"{ref.name} ({ref.symbol.upper()})\n"
        f"Fiyat: {price(snapshot.price_usd)}\n"
        f"24s: {pct(snapshot.change_24h_pct, signed=True)} | 7g: {pct(snapshot.change_7d_pct, signed=True)}\n"
        f"Piyasa değeri: {money(snapshot.market_cap_usd)} | Sıra: #{snapshot.rank or '—'}"
    )


def _latest_run_reply(db: Database, coin: str) -> str:
    rows = db.run_summaries(coin=coin, limit=1)
    if not rows:
        return f"{coin.upper()} için kayıtlı derin araştırma yok. /arastir {coin} ile başlatabilirsiniz."
    run = rows[-1]
    return (
        f"{run.get('symbol') or coin.upper()} son araştırması\n"
        f"Skor: {score(run.get('weighted_score'))} | Yükseliş: %{float(run.get('up_probability') or 50):.1f}\n"
        f"Profil: {run.get('profile') or 'balanced'} | Zaman dilimi: {run.get('timeframe') or '1d'}\n"
        f"Rapor: /rapor {coin}"
    )


def _latest_report_reply(db: Database, coin: str) -> str:
    reports = db.list_reports(limit=50)
    match = next((row for row in reports if str(row.get("coin") or "").lower() == coin.lower()), None)
    if not match:
        return f"{coin.upper()} için rapor bulunamadı. /arastir {coin} ile oluşturabilirsiniz."
    data = db.get_report(match["name"])
    markdown = (data or {}).get("markdown") or ""
    header = f"{match['name']}\n\n"
    return header + markdown[: MAX_MESSAGE - len(header) - 20]


async def handle_message(text: str) -> str:
    """Komutu isler ve gonderilecek yanit metnini dondurur."""
    command, args = parse_command(text)
    if command in ("", "start", "yardim", "help"):
        return HELP_TEXT
    if not args and command in ("fiyat", "skor", "rapor", "arastir"):
        return f"Kullanim: /{command} <coin>"
    settings = get_settings()
    db = Database(settings.db_path)
    coin = args[0] if args else ""
    if command == "fiyat":
        providers = build_providers(settings, db)
        try:
            return await _snapshot_reply(providers, settings, coin)
        except Exception as exc:
            return f"Fiyat alınamadı: {exc}"
        finally:
            await providers.aclose()
    if command == "skor":
        return _latest_run_reply(db, coin)
    if command == "rapor":
        return _latest_report_reply(db, coin)
    if command == "arastir":
        profile = PROFILE_ALIASES.get(args[1].lower(), "balanced") if len(args) > 1 else "balanced"
        providers = build_providers(settings, db)
        engine = DeepResearchEngine(providers, settings, db)
        try:
            output = await engine.run(coin, profile=profile, include_all_items=True)
            run = output.run
            return (
                f"{run.coin.name} ({run.coin.symbol.upper()}) araştırması tamamlandı\n"
                f"Skor: {score(run.weighted_score)} | Yükseliş: %{run.up_probability:.1f} | "
                f"Düşüş: %{run.down_probability:.1f}\n"
                f"Beklenen aralık: {price(run.expected_low)} – {price(run.expected_high)}\n"
                f"Rapor: {output.report_path}"
            )
        except Exception as exc:
            return f"Araştırma başarısız: {exc}"
        finally:
            await providers.aclose()
    return HELP_TEXT


async def run_bot(token: str | None = None, poll_timeout: int = 30) -> None:
    """Uzun yoklamali Telegram botu; ilk gelen mesajdan itibaren yanit verir."""
    settings = get_settings()
    token = token or settings.telegram_token
    if not token:
        raise RuntimeError(
            "Telegram token bulunamadı. CDR_TELEGRAM_TOKEN tanımlayın veya --token verin."
        )
    offset = 0
    logger.info("Telegram botu başladı; komutlar için /yardim")
    async with httpx.AsyncClient(timeout=poll_timeout + 15) as client:
        while True:
            try:
                data = await _call(
                    client, token, "getUpdates", offset=offset, timeout=poll_timeout
                )
            except Exception as exc:
                logger.warning("Telegram baglanti hatasi: %s", exc)
                await asyncio.sleep(5)
                continue
            for update in data.get("result") or []:
                offset = max(offset, int(update.get("update_id", 0)) + 1)
                message = update.get("message") or update.get("edited_message") or {}
                chat_id = (message.get("chat") or {}).get("id")
                text = message.get("text") or ""
                if not chat_id or not text:
                    continue
                try:
                    reply = await handle_message(text)
                except Exception as exc:
                    logger.exception("Telegram komut hatasi")
                    reply = f"Beklenmeyen hata: {exc}"
                await _send(client, token, chat_id, reply)
