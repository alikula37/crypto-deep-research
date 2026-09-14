"""Kosu arsivleme: eski kosulari ayri bir SQLite dosyasina tasir.

Turev tablolar (feature_snapshots, item_features, outcomes) asla arsivlenmez;
egitim verisi ana veritabaninda kalir.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

ARCHIVE_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  coin TEXT,
  created_at REAL,
  payload TEXT
);
CREATE TABLE IF NOT EXISTS reports (
  name TEXT PRIMARY KEY,
  run_id TEXT,
  coin TEXT,
  created_at REAL,
  markdown TEXT,
  meta TEXT
);
"""


def archive_runs(
    db,
    *,
    archive_path: str | Path,
    older_than_days: int = 540,
    delete: bool = False,
    now: float | None = None,
) -> dict[str, Any]:
    """Kesim tarihinden eski kosulari ve raporlari arsive kopyalar; opsiyonel siler."""
    cutoff = (now or time.time()) - older_than_days * 86_400
    runs = db.runs_to_archive(cutoff)
    reports = db.reports_to_archive(cutoff)
    path = Path(archive_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not runs and not reports:
        return {
            "runs": 0,
            "reports": 0,
            "deleted": False,
            "path": str(path),
            "cutoff": cutoff,
        }

    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(ARCHIVE_SCHEMA)
        connection.executemany(
            "INSERT OR REPLACE INTO runs (run_id, coin, created_at, payload) VALUES (?, ?, ?, ?)",
            [(row["run_id"], row["coin"], row["created_at"], row["payload"]) for row in runs],
        )
        connection.executemany(
            """
            INSERT OR REPLACE INTO reports (name, run_id, coin, created_at, markdown, meta)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["name"], row.get("run_id"), row.get("coin"),
                    row.get("created_at"), row.get("markdown"), row.get("meta"),
                )
                for row in reports
            ],
        )
        connection.commit()
    finally:
        connection.close()

    deleted = 0
    if delete:
        deleted = db.delete_runs([row["run_id"] for row in runs])
        deleted += db.delete_reports([row["name"] for row in reports])

    return {
        "runs": len(runs),
        "reports": len(reports),
        "deleted": deleted,
        "path": str(path),
        "cutoff": cutoff,
    }
