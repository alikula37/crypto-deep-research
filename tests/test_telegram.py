"""Telegram botu komut ayristirma ve cevrimdisi yanit testleri."""

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
