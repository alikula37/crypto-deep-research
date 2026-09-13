"""Kayitli promptlara erisim: bir coin icin en son uretilen promptu bulur ve okur."""

from __future__ import annotations

import json
from pathlib import Path

from crypto_deep_research.config import Settings
from crypto_deep_research.storage.db import Database


def _read_prompt(path: str | Path) -> str | None:
    candidate = Path(path)
    if candidate.exists():
        return candidate.read_text(encoding="utf-8")
    return None


def _meta_of(data: dict | None) -> dict:
    if not data:
        return {}
    meta = data.get("meta")
    if isinstance(meta, str):
        try:
            return json.loads(meta)
        except (ValueError, TypeError):
            return {}
    return meta or {}


def prompt_for_report(db: Database, settings: Settings, name: str) -> dict | None:
    """Rapor adindan prompt metnini bulur (DB meta yolu, sonra dosya kalibi)."""
    data = db.get_report(name)
    meta = _meta_of(data)
    for path in (meta.get("prompt_path"), settings.prompts_dir / f"{name}_prompt.txt"):
        if not path:
            continue
        text = _read_prompt(path)
        if text:
            return {"name": name, "path": str(path), "prompt": text}
    return None


def latest_prompt(
    db: Database, settings: Settings, coin: str, symbol: str | None = None
) -> dict | None:
    """Coin icin en son prompt: once DB meta yolu, sonra dosya adi kalibi denenir."""
    wanted = (coin or "").strip().lower()
    if not wanted:
        return None
    for row in db.list_reports(limit=200):
        if str(row.get("coin") or "").lower() != wanted:
            continue
        data = db.get_report(row["name"])
        meta = _meta_of(data)
        for path in (meta.get("prompt_path"), settings.prompts_dir / f"{row['name']}_prompt.txt"):
            if not path:
                continue
            text = _read_prompt(path)
            if text:
                return {"name": row["name"], "coin": wanted, "path": str(path), "prompt": text}
    # DB kaydi yoksa/eskimisse: dosya sistemi (SYMBOL_tarih_prompt.txt)
    prefixes = {wanted.upper()}
    if symbol:
        prefixes.add(symbol.strip().upper())
    for path in sorted(
        settings.prompts_dir.glob("*_prompt.txt"), key=lambda p: p.stat().st_mtime, reverse=True
    ):
        stem = path.stem.replace("_prompt", "")
        if any(stem.upper().startswith(prefix + "_") for prefix in prefixes):
            text = _read_prompt(path)
            if text:
                return {"name": stem, "coin": wanted, "path": str(path), "prompt": text}
    return None
