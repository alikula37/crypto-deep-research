"""Telegram botu komut ayristirma ve cevrimdisi yanit testleri."""

import respx

from crypto_deep_research.telegram_bot import (
    HELP_TEXT,
    PROFILE_ALIASES,
    handle_message,
    parse_command,
)


def test_parse_command_basic():
    assert parse_command("/fiyat BTC") == ("fiyat", ["BTC"])
    assert parse_command("/arastir bitcoin muhafazakar") == ("arastir", ["bitcoin", "muhafazakar"])
    assert parse_command("/yardim@crypto_bot") == ("yardim", [])
    assert parse_command("merhaba") == ("", [])


def test_parse_command_trims_spaces():
    assert parse_command("  /skor   eth  ") == ("skor", ["eth"])


async def test_help_and_usage_without_network():
    assert await handle_message("/start") == HELP_TEXT
    assert await handle_message("selam") == HELP_TEXT
    assert (await handle_message("/fiyat")).startswith("Kullanim")
    assert (await handle_message("/arastir")).startswith("Kullanim")


def test_profile_aliases():
    assert PROFILE_ALIASES["muhafazakar"] == "conservative"
    assert PROFILE_ALIASES["dengeli"] == "balanced"
    assert PROFILE_ALIASES["agresif"] == "aggressive"


@respx.mock
async def test_fetch_bot_info_validates_token():
    import httpx
    import pytest
    import respx

    from crypto_deep_research.telegram_bot import fetch_bot_info

    respx.post("https://api.telegram.org/bot123:ABC/getMe").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"username": "cdr_bot"}})
    )
    info = await fetch_bot_info("123:ABC")
    assert info["username"] == "cdr_bot"

    respx.post("https://api.telegram.org/botbad/getMe").mock(
        return_value=httpx.Response(200, json={"ok": False, "description": "Unauthorized"})
    )
    with pytest.raises(RuntimeError):
        await fetch_bot_info("bad")


async def test_bot_manager_start_stop(monkeypatch):
    import asyncio

    from crypto_deep_research.telegram_bot import TelegramBotManager

    async def fake_run_bot(token, poll_timeout=30):
        await asyncio.sleep(60)

    async def fake_info(token):
        return {"username": "test_bot"}

    monkeypatch.setattr("crypto_deep_research.telegram_bot.run_bot", fake_run_bot)
    monkeypatch.setattr("crypto_deep_research.telegram_bot.fetch_bot_info", fake_info)

    manager = TelegramBotManager()
    status = await manager.start("token")
    assert status["running"] is True
    assert manager.username == "test_bot"
    stopped = await manager.stop()
    assert stopped["running"] is False
    assert manager.error is None
