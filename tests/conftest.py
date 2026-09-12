"""Ortak test yardimcilari: ayarlar, veritabani ve hizli onbellekli HTTP istemcisi."""

from __future__ import annotations

import pytest

from crypto_deep_research.config import Settings
from crypto_deep_research.providers.base import MIN_INTERVALS, CachedHTTP
from crypto_deep_research.storage.db import Database


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path)


@pytest.fixture
def db(settings: Settings) -> Database:
    return Database(settings.db_path)


@pytest.fixture
async def http(db: Database, settings: Settings, monkeypatch):
    """Rate limit beklemelerini sifirlayan, tek denemeli istemci."""
    for provider in list(MIN_INTERVALS):
        monkeypatch.setitem(MIN_INTERVALS, provider, 0.0)
    settings.http_retries = 1
    client = CachedHTTP(db, settings)
    yield client
    await client.aclose()
