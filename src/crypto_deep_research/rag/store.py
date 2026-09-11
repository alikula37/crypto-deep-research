"""LanceDB tabanli yerel vektor deposu; kullanilamazsa SQLite FTS'e duser."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TABLE_NAME = "documents"


class VectorStore:
    """LanceDB sarmalayicisi. Basarisizlikta available False olur ve FTS kullanilir."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.available = False
        self._db: Any | None = None
        try:
            import lancedb

            self.directory.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(str(self.directory))
            self.available = True
        except Exception as exc:
            logger.warning("LanceDB kullanilamiyor, FTS'e dusuluyor: %s", exc)

    def _table(self) -> Any:
        if not self.available or self._db is None:
            return None
        try:
            if TABLE_NAME in self._db.table_names():
                return self._db.open_table(TABLE_NAME)
            return None
        except Exception as exc:
            logger.warning("LanceDB tablo hatasi: %s", exc)
            return None

    def add(self, rows: list[dict[str, Any]]) -> bool:
        if not rows:
            return False
        table = self._table()
        try:
            if table is None:
                self._db.create_table(TABLE_NAME, data=rows)
            else:
                table.add(rows)
            return True
        except Exception as exc:
            logger.warning("LanceDB yazma hatasi: %s", exc)
            self.available = False
            return False

    def search(
        self, vector: list[float], k: int = 8, coin: str | None = None
    ) -> list[dict[str, Any]]:
        table = self._table()
        if table is None:
            return []
        try:
            query = table.search(vector).limit(k)
            if coin:
                query = query.where(f"coin = '{coin}'")
            rows = query.to_list()
            for row in rows:
                distance = float(row.pop("_distance", 0.0) or 0.0)
                row["score"] = 1.0 / (1.0 + distance)
            return rows
        except Exception as exc:
            logger.warning("LanceDB arama hatasi: %s", exc)
            return []

    def count(self) -> int:
        table = self._table()
        if table is None:
            return 0
        try:
            return int(table.count_rows())
        except Exception:
            return 0


def make_doc_id(prefix: str, value: str) -> str:
    import hashlib

    digest = hashlib.sha1(f"{prefix}:{value}".encode()).hexdigest()
    return f"{prefix}-{digest[:24]}"


def now_ts() -> float:
    return time.time()
