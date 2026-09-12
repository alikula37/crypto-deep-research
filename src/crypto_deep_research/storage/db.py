"""SQLite tabanlı depolama: önbellek, makale, context, kosu ve rapor kayıtları."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from crypto_deep_research.models import (
    ContextObject,
    NewsArticle,
    ResearchRun,
    utcnow,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS http_cache (
  key TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  url TEXT NOT NULL,
  params TEXT,
  payload TEXT,
  status INTEGER,
  created_at REAL NOT NULL,
  ttl INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_http_cache_provider ON http_cache(provider);

CREATE TABLE IF NOT EXISTS snapshots (
  coin TEXT PRIMARY KEY,
  fetched_at REAL NOT NULL,
  payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS articles (
  id TEXT PRIMARY KEY,
  coin TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  source TEXT,
  published_at REAL,
  summary TEXT,
  sentiment REAL,
  payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_articles_coin_time ON articles(coin, published_at DESC);

CREATE TABLE IF NOT EXISTS context_objects (
  key TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  scope TEXT,
  content TEXT,
  blob_ref TEXT,
  data TEXT,
  provenance TEXT,
  ttl INTEGER,
  version INTEGER DEFAULT 1,
  tokens INTEGER DEFAULT 0,
  priority REAL DEFAULT 1.0,
  pinned INTEGER DEFAULT 0,
  state TEXT DEFAULT 'hot',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_context_scope ON context_objects(kind);

CREATE TABLE IF NOT EXISTS blobs (
  key TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  coin TEXT NOT NULL,
  created_at REAL NOT NULL,
  payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_coin ON runs(coin, created_at DESC);

CREATE TABLE IF NOT EXISTS metric_history (
  coin TEXT NOT NULL,
  metric TEXT NOT NULL,
  value REAL NOT NULL,
  ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metric_history ON metric_history(coin, metric, ts DESC);

CREATE TABLE IF NOT EXISTS reports (
  name TEXT PRIMARY KEY,
  run_id TEXT,
  coin TEXT,
  created_at REAL NOT NULL,
  markdown TEXT NOT NULL,
  meta TEXT
);

CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  coin TEXT,
  kind TEXT,
  source TEXT,
  url TEXT,
  text TEXT NOT NULL,
  ts REAL
);
CREATE INDEX IF NOT EXISTS idx_documents_coin ON documents(coin, kind);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
  doc_id UNINDEXED, coin UNINDEXED, source UNINDEXED, text
);
"""


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: str | None) -> Any:
    if value is None:
        return None
    return json.loads(value)


def stable_key(*parts: Any) -> str:
    """Verilen parcalardan deterministik bir anahtar üretir."""
    raw = "|".join(_dumps(p) if not isinstance(p, str) else p for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


class Database:
    """Küçük, thread-safe SQLite sarmalayicisi."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(SCHEMA)

    # ------------------------------------------------------------------ temel
    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        with self._lock, self._conn:
            return self._conn.execute(sql, params)

    def query(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ cache
    def cache_get(self, key: str, ttl: int | None = None) -> tuple[Any, bool] | None:
        """(payload, is_fresh) döndürür; yoksa None."""
        rows = self.query("SELECT payload, created_at, ttl FROM http_cache WHERE key = ?", (key,))
        if not rows:
            return None
        row = rows[0]
        effective_ttl = ttl if ttl is not None else row["ttl"]
        fresh = (time.time() - row["created_at"]) < effective_ttl
        return _loads(row["payload"]), fresh

    def cache_set(
        self,
        key: str,
        provider: str,
        url: str,
        payload: Any,
        ttl: int,
        params: dict | None = None,
        status: int = 200,
    ) -> None:
        self.execute(
            """
            INSERT OR REPLACE INTO http_cache
                (key, provider, url, params, payload, status, created_at, ttl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (key, provider, url, _dumps(params or {}), _dumps(payload), status, time.time(), ttl),
        )

    def cache_clear(self, provider: str | None = None) -> int:
        if provider:
            cur = self.execute("DELETE FROM http_cache WHERE provider = ?", (provider,))
        else:
            cur = self.execute("DELETE FROM http_cache")
        return cur.rowcount

    def cache_stats(self) -> list[dict[str, Any]]:
        return self.query(
            "SELECT provider, COUNT(*) AS entries, MAX(created_at) AS last_at FROM http_cache GROUP BY provider"
        )

    def prune_cache(self, max_age_seconds: int = 7 * 86400) -> int:
        cutoff = time.time() - max_age_seconds
        return self.execute("DELETE FROM http_cache WHERE created_at < ?", (cutoff,)).rowcount

    # ------------------------------------------------------------------ snapshot
    def save_snapshot(self, coin: str, payload: dict) -> None:
        self.execute(
            "INSERT OR REPLACE INTO snapshots (coin, fetched_at, payload) VALUES (?, ?, ?)",
            (coin, time.time(), _dumps(payload)),
        )

    def get_snapshot(self, coin: str) -> dict | None:
        rows = self.query("SELECT payload, fetched_at FROM snapshots WHERE coin = ?", (coin,))
        if not rows:
            return None
        payload = _loads(rows[0]["payload"])
        payload["_cached_at"] = rows[0]["fetched_at"]
        return payload

    # ------------------------------------------------------------------ articles
    def save_articles(self, coin: str, articles: list[NewsArticle]) -> int:
        saved = 0
        for article in articles:
            article_id = article.url or article.title
            aid = hashlib.sha1(article_id.encode("utf-8")).hexdigest()
            published = article.published_at.timestamp() if article.published_at else None
            self.execute(
                """
                INSERT OR REPLACE INTO articles
                    (id, coin, title, url, source, published_at, summary, sentiment, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    aid,
                    coin,
                    article.title,
                    article.url,
                    article.source,
                    published,
                    article.summary,
                    article.sentiment,
                    article.model_dump_json(),
                ),
            )
            saved += 1
        return saved

    def get_articles(
        self, coin: str, hours: int = 168, limit: int = 200
    ) -> list[NewsArticle]:
        cutoff = time.time() - hours * 3600
        rows = self.query(
            """
            SELECT payload FROM articles
            WHERE coin = ? AND (published_at IS NULL OR published_at >= ?)
            ORDER BY COALESCE(published_at, 0) DESC
            LIMIT ?
            """,
            (coin, cutoff, limit),
        )
        result: list[NewsArticle] = []
        for row in rows:
            try:
                result.append(NewsArticle.model_validate_json(row["payload"]))
            except Exception:
                continue
        return result

    # ------------------------------------------------------------------ context
    def save_context(self, obj: ContextObject) -> None:
        scope = _dumps(obj.scope)
        existing = self.query(
            "SELECT version, created_at FROM context_objects WHERE key = ?", (obj.key,)
        )
        version = obj.version
        created = obj.created_at.timestamp()
        if existing:
            version = max(version, existing[0]["version"] + 1)
            created = existing[0]["created_at"]
        self.execute(
            """
            INSERT OR REPLACE INTO context_objects
                (key, kind, scope, content, blob_ref, data, provenance, ttl, version,
                 tokens, priority, pinned, state, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                obj.key,
                obj.kind,
                scope,
                obj.content,
                obj.blob_ref,
                _dumps(obj.data),
                _dumps([s.model_dump(mode="json") for s in obj.provenance]),
                obj.ttl_seconds,
                version,
                obj.tokens_estimate,
                obj.priority,
                1 if obj.pinned else 0,
                obj.state,
                created,
                utcnow().timestamp(),
            ),
        )

    def get_context(self, key: str) -> ContextObject | None:
        rows = self.query("SELECT * FROM context_objects WHERE key = ?", (key,))
        if not rows:
            return None
        return self._context_from_row(rows[0])

    def list_contexts(
        self, kind: str | None = None, scope_contains: str | None = None, limit: int = 500
    ) -> list[ContextObject]:
        sql = "SELECT * FROM context_objects"
        params: list[Any] = []
        clauses = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if scope_contains:
            clauses.append("scope LIKE ?")
            params.append(f"%{scope_contains}%")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        return [self._context_from_row(row) for row in self.query(sql, tuple(params))]

    def delete_context(self, key: str) -> None:
        self.execute("DELETE FROM context_objects WHERE key = ?", (key,))

    @staticmethod
    def _context_from_row(row: dict[str, Any]) -> ContextObject:
        from crypto_deep_research.models import SourceRef

        provenance = []
        for item in _loads(row["provenance"]) or []:
            try:
                provenance.append(SourceRef.model_validate(item))
            except Exception:
                continue
        return ContextObject(
            key=row["key"],
            kind=row["kind"],
            scope=_loads(row["scope"]) or {},
            content=row["content"] or "",
            blob_ref=row["blob_ref"],
            data=_loads(row["data"]) or {},
            provenance=provenance,
            ttl_seconds=row["ttl"],
            version=row["version"] or 1,
            tokens_estimate=row["tokens"] or 0,
            priority=row["priority"] or 1.0,
            pinned=bool(row["pinned"]),
            state=row["state"] or "hot",
        )

    # ------------------------------------------------------------------ blobs (offload)
    def save_blob(self, key: str, payload: Any) -> str:
        self.execute(
            "INSERT OR REPLACE INTO blobs (key, payload, created_at) VALUES (?, ?, ?)",
            (key, _dumps(payload), time.time()),
        )
        return key

    def get_blob(self, key: str) -> Any | None:
        rows = self.query("SELECT payload FROM blobs WHERE key = ?", (key,))
        return _loads(rows[0]["payload"]) if rows else None

    # ------------------------------------------------------------------ runs
    def save_run(self, run: ResearchRun) -> None:
        self.execute(
            "INSERT OR REPLACE INTO runs (run_id, coin, created_at, payload) VALUES (?, ?, ?, ?)",
            (run.run_id, run.coin.id, run.created_at.timestamp(), run.model_dump_json()),
        )

    def get_run(self, run_id: str) -> ResearchRun | None:
        rows = self.query("SELECT payload FROM runs WHERE run_id = ?", (run_id,))
        return ResearchRun.model_validate_json(rows[0]["payload"]) if rows else None

    def list_runs(self, coin: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if coin:
            return self.query(
                "SELECT run_id, coin, created_at FROM runs WHERE coin = ? ORDER BY created_at DESC LIMIT ?",
                (coin, limit),
            )
        return self.query(
            "SELECT run_id, coin, created_at FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        )

    def run_summaries(self, coin: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Kosu ozetleri: skor gecmisi grafikleri icin hafif alanlar (eskiden yeniye)."""
        if coin:
            rows = self.query(
                "SELECT run_id, coin, created_at, payload FROM runs WHERE coin = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (coin, limit),
            )
        else:
            rows = self.query(
                "SELECT run_id, coin, created_at, payload FROM runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        summaries: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload"])
            except (ValueError, TypeError):
                continue
            summaries.append(
                {
                    "run_id": row["run_id"],
                    "coin": row["coin"],
                    "symbol": ((payload.get("coin") or {}).get("symbol") or "").upper(),
                    "created_at": row["created_at"],
                    "timeframe": payload.get("timeframe"),
                    "weighted_score": payload.get("weighted_score"),
                    "up_probability": payload.get("up_probability"),
                    "down_probability": payload.get("down_probability"),
                    "current_price": payload.get("current_price"),
                }
            )
        summaries.reverse()
        return summaries

    # ------------------------------------------------------------------ metric geçmişi
    def record_metric(self, coin: str, metric: str, value: float, ts: float | None = None) -> None:
        self.execute(
            "INSERT INTO metric_history (coin, metric, value, ts) VALUES (?, ?, ?, ?)",
            (coin, metric, float(value), ts or time.time()),
        )

    def metric_history(self, coin: str, metric: str, limit: int = 500) -> list[dict[str, Any]]:
        return self.query(
            """
            SELECT value, ts FROM metric_history
            WHERE coin = ? AND metric = ?
            ORDER BY ts DESC LIMIT ?
            """,
            (coin, metric, limit),
        )

    # ------------------------------------------------------------------ reports
    def save_report(self, name: str, run_id: str, coin: str, markdown: str, meta: dict) -> None:
        self.execute(
            "INSERT OR REPLACE INTO reports (name, run_id, coin, created_at, markdown, meta) VALUES (?, ?, ?, ?, ?, ?)",
            (name, run_id, coin, time.time(), markdown, _dumps(meta)),
        )

    def get_report(self, name: str) -> dict[str, Any] | None:
        rows = self.query("SELECT * FROM reports WHERE name = ?", (name,))
        return rows[0] if rows else None

    def list_reports(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.query(
            "SELECT name, run_id, coin, created_at FROM reports ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )

    # ------------------------------------------------------------------ documents (FTS)
    def save_document(
        self,
        doc_id: str,
        coin: str | None,
        kind: str,
        source: str | None,
        url: str | None,
        text: str,
        ts: float | None = None,
    ) -> None:
        self.execute(
            "INSERT OR REPLACE INTO documents (id, coin, kind, source, url, text, ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (doc_id, coin, kind, source, url, text, ts or time.time()),
        )
        self.execute("DELETE FROM documents_fts WHERE doc_id = ?", (doc_id,))
        self.execute(
            "INSERT INTO documents_fts (doc_id, coin, source, text) VALUES (?, ?, ?, ?)",
            (doc_id, coin, source, text),
        )

    def search_documents(
        self, query: str, coin: str | None = None, limit: int = 8
    ) -> list[dict[str, Any]]:
        terms = [term for term in query.replace('"', " ").split() if len(term) > 1]
        if not terms:
            return []
        fts_query = " OR ".join(f'"{term}"' for term in terms)
        try:
            if coin:
                rows = self.query(
                    """
                    SELECT d.*, bm25(documents_fts) AS rank
                    FROM documents_fts
                    JOIN documents d ON d.id = documents_fts.doc_id
                    WHERE documents_fts MATCH ? AND d.coin = ?
                    ORDER BY rank LIMIT ?
                    """,
                    (fts_query, coin, limit),
                )
            else:
                rows = self.query(
                    """
                    SELECT d.*, bm25(documents_fts) AS rank
                    FROM documents_fts
                    JOIN documents d ON d.id = documents_fts.doc_id
                    WHERE documents_fts MATCH ?
                    ORDER BY rank LIMIT ?
                    """,
                    (fts_query, limit),
                )
        except sqlite3.OperationalError:
            like = f"%{query}%"
            if coin:
                rows = self.query(
                    "SELECT * FROM documents WHERE text LIKE ? AND coin = ? ORDER BY ts DESC LIMIT ?",
                    (like, coin, limit),
                )
            else:
                rows = self.query(
                    "SELECT * FROM documents WHERE text LIKE ? ORDER BY ts DESC LIMIT ?",
                    (like, limit),
                )
        return rows

    def document_count(self) -> int:
        rows = self.query("SELECT COUNT(*) AS n FROM documents")
        return rows[0]["n"] if rows else 0
