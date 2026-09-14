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

CREATE TABLE IF NOT EXISTS watchlist (
  coin TEXT PRIMARY KEY,
  symbol TEXT,
  name TEXT,
  profile TEXT NOT NULL DEFAULT 'balanced',
  timeframe TEXT NOT NULL DEFAULT '1d',
  auto_run INTEGER NOT NULL DEFAULT 1,
  added_at REAL NOT NULL,
  last_run_at REAL
);

CREATE TABLE IF NOT EXISTS portfolio (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  coin TEXT NOT NULL,
  symbol TEXT,
  name TEXT,
  amount REAL NOT NULL,
  entry_price REAL NOT NULL,
  entry_date REAL,
  note TEXT,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  progress INTEGER NOT NULL DEFAULT 0,
  message TEXT,
  created_at REAL NOT NULL,
  finished_at REAL,
  error TEXT,
  result TEXT
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

CREATE TABLE IF NOT EXISTS feature_snapshots (
  run_id TEXT PRIMARY KEY,
  coin TEXT NOT NULL,
  created_at REAL NOT NULL,
  profile TEXT NOT NULL DEFAULT 'balanced',
  feature_schema_version INTEGER NOT NULL DEFAULT 1,
  n_ok INTEGER NOT NULL DEFAULT 0,
  n_partial INTEGER NOT NULL DEFAULT 0,
  n_no_data INTEGER NOT NULL DEFAULT 0,
  n_error INTEGER NOT NULL DEFAULT 0,
  coverage_ratio REAL,
  coverage_weighted REAL,
  weighted_score REAL,
  signal_strength REAL,
  score_mean REAL,
  score_dispersion REAL,
  confidence_mean REAL,
  category_scores TEXT,
  atr_pct REAL,
  regime TEXT,
  volatility_bucket TEXT,
  current_price REAL,
  up_probability REAL,
  down_probability REAL,
  expected_low REAL,
  expected_high REAL,
  items_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_feature_snapshots_coin_time ON feature_snapshots(coin, created_at DESC);

CREATE TABLE IF NOT EXISTS item_features (
  run_id TEXT NOT NULL,
  item_id INTEGER NOT NULL,
  coin TEXT NOT NULL,
  category TEXT,
  source TEXT,
  weight REAL,
  score REAL,
  confidence REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  contribution REAL,
  PRIMARY KEY (run_id, item_id)
);
CREATE INDEX IF NOT EXISTS idx_item_features_item ON item_features(item_id, coin);

CREATE TABLE IF NOT EXISTS outcomes (
  run_id TEXT NOT NULL,
  horizon_days INTEGER NOT NULL,
  coin TEXT NOT NULL,
  symbol TEXT,
  entry_price REAL,
  entry_at REAL NOT NULL,
  target_date TEXT NOT NULL,
  due_at REAL NOT NULL,
  exit_price REAL,
  return_pct REAL,
  hit INTEGER,
  direction_at_run TEXT,
  weighted_score REAL,
  price_source TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_attempt_at REAL,
  filled_at REAL,
  note TEXT,
  PRIMARY KEY (run_id, horizon_days)
);
CREATE INDEX IF NOT EXISTS idx_outcomes_due ON outcomes(status, due_at);
CREATE INDEX IF NOT EXISTS idx_outcomes_coin ON outcomes(coin, horizon_days, target_date DESC);

CREATE TABLE IF NOT EXISTS model_registry (
  model_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  horizon_days INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'shadow',
  trained_at REAL,
  train_rows INTEGER,
  feature_schema_version INTEGER NOT NULL DEFAULT 1,
  params TEXT,
  metrics TEXT,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS calibration_bins (
  model_id TEXT NOT NULL,
  horizon_days INTEGER NOT NULL,
  bin_index INTEGER NOT NULL,
  bin_low REAL NOT NULL,
  bin_high REAL NOT NULL,
  n INTEGER NOT NULL DEFAULT 0,
  predicted_mean REAL,
  observed_rate REAL,
  ci_low REAL,
  ci_high REAL,
  computed_at REAL NOT NULL,
  PRIMARY KEY (model_id, horizon_days, bin_index)
);

CREATE TABLE IF NOT EXISTS predictions (
  run_id TEXT NOT NULL,
  horizon_days INTEGER NOT NULL,
  model_id TEXT NOT NULL,
  heuristic_up REAL,
  probability_up REAL NOT NULL,
  probability_down REAL NOT NULL,
  n_train INTEGER,
  calibration_n INTEGER,
  calibration_observed REAL,
  is_shadow INTEGER NOT NULL DEFAULT 1,
  created_at REAL NOT NULL,
  PRIMARY KEY (run_id, horizon_days, model_id)
);

CREATE TABLE IF NOT EXISTS drift_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  computed_at REAL NOT NULL,
  window_label TEXT NOT NULL,
  metric TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT 'global',
  value REAL,
  baseline REAL,
  delta REAL,
  psi REAL,
  n INTEGER,
  alarm INTEGER NOT NULL DEFAULT 0,
  threshold REAL,
  details TEXT
);
CREATE INDEX IF NOT EXISTS idx_drift_metrics_lookup ON drift_metrics(metric, scope, computed_at DESC);

CREATE TABLE IF NOT EXISTS scheduled_jobs (
  job_key TEXT PRIMARY KEY,
  last_started_at REAL,
  last_finished_at REAL,
  last_status TEXT,
  lease_until REAL,
  cursor TEXT,
  last_error TEXT,
  run_count INTEGER NOT NULL DEFAULT 0
);

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
        self._ensure_column("feature_snapshots", "source", "TEXT DEFAULT 'live'")
        self._ensure_column("outcomes", "source", "TEXT DEFAULT 'live'")

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
                    "expected_low": payload.get("expected_low"),
                    "expected_high": payload.get("expected_high"),
                    "current_price": payload.get("current_price"),
                }
            )
        summaries.reverse()
        return summaries

    # ------------------------------------------------------------------ takip listesi
    def watchlist_add(
        self,
        coin: str,
        *,
        symbol: str | None = None,
        name: str | None = None,
        profile: str = "balanced",
        timeframe: str = "1d",
        auto_run: bool = True,
    ) -> None:
        self.execute(
            """
            INSERT INTO watchlist (coin, symbol, name, profile, timeframe, auto_run, added_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(coin) DO UPDATE SET
              symbol = COALESCE(excluded.symbol, watchlist.symbol),
              name = COALESCE(excluded.name, watchlist.name),
              profile = excluded.profile,
              timeframe = excluded.timeframe,
              auto_run = excluded.auto_run
            """,
            (coin, symbol, name, profile, timeframe, 1 if auto_run else 0, time.time()),
        )

    def watchlist_remove(self, coin: str) -> None:
        self.execute("DELETE FROM watchlist WHERE coin = ?", (coin,))

    def watchlist_get(self, coin: str) -> dict[str, Any] | None:
        rows = self.query("SELECT * FROM watchlist WHERE coin = ?", (coin,))
        if not rows:
            return None
        row = rows[0]
        row["auto_run"] = bool(row["auto_run"])
        return row

    def watchlist_list(self) -> list[dict[str, Any]]:
        rows = self.query("SELECT * FROM watchlist ORDER BY added_at")
        for row in rows:
            row["auto_run"] = bool(row["auto_run"])
            last = self.query("SELECT MAX(created_at) AS ts FROM runs WHERE coin = ?", (row["coin"],))
            run_ts = last[0]["ts"] if last and last[0]["ts"] else None
            # Deneme isareti (touch) ile tamamlanan son kosunun en yenisi gecerlidir;
            # aksi halde eski kosu tarihi touch'i ezip scheduler'i tekrar tetikler.
            candidates = [value for value in (row.get("last_run_at"), run_ts) if value is not None]
            row["last_run_at"] = max(candidates) if candidates else None
        return rows

    def watchlist_touch(self, coin: str, ts: float | None = None) -> None:
        self.execute(
            "UPDATE watchlist SET last_run_at = ? WHERE coin = ?", (ts or time.time(), coin)
        )

    # ------------------------------------------------------------------ portfoy
    def portfolio_add(
        self,
        coin: str,
        *,
        amount: float,
        entry_price: float,
        symbol: str | None = None,
        name: str | None = None,
        entry_date: float | None = None,
        note: str | None = None,
    ) -> int:
        cursor = self.execute(
            """
            INSERT INTO portfolio (coin, symbol, name, amount, entry_price, entry_date, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (coin, symbol, name, float(amount), float(entry_price), entry_date, note, time.time()),
        )
        return int(cursor.lastrowid or 0)

    def portfolio_list(self) -> list[dict[str, Any]]:
        return self.query("SELECT * FROM portfolio ORDER BY created_at")

    def portfolio_get(self, position_id: int) -> dict[str, Any] | None:
        rows = self.query("SELECT * FROM portfolio WHERE id = ?", (position_id,))
        return rows[0] if rows else None

    def portfolio_update(
        self,
        position_id: int,
        *,
        amount: float | None = None,
        entry_price: float | None = None,
        note: str | None = None,
    ) -> None:
        entry = self.portfolio_get(position_id)
        if not entry:
            return
        self.execute(
            "UPDATE portfolio SET amount = ?, entry_price = ?, note = ? WHERE id = ?",
            (
                amount if amount is not None else entry["amount"],
                entry_price if entry_price is not None else entry["entry_price"],
                note if note is not None else entry["note"],
                position_id,
            ),
        )

    def portfolio_remove(self, position_id: int) -> None:
        self.execute("DELETE FROM portfolio WHERE id = ?", (position_id,))

    # ------------------------------------------------------------------ isler (jobs)
    def job_save(self, payload: dict[str, Any]) -> None:
        result = payload.get("result")
        self.execute(
            """
            INSERT OR REPLACE INTO jobs
              (id, status, progress, message, created_at, finished_at, error, result)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["job_id"],
                payload.get("status") or "queued",
                int(payload.get("progress") or 0),
                payload.get("message"),
                payload.get("created_at") or time.time(),
                payload.get("finished_at"),
                payload.get("error"),
                _dumps(result) if result is not None else None,
            ),
        )

    def job_get(self, job_id: str) -> dict[str, Any] | None:
        rows = self.query("SELECT * FROM jobs WHERE id = ?", (job_id,))
        if not rows:
            return None
        row = rows[0]
        payload: dict[str, Any] = {
            "job_id": row["id"],
            "status": row["status"],
            "progress": row["progress"],
            "message": row["message"],
            "created_at": row["created_at"],
            "finished_at": row["finished_at"],
        }
        if row.get("error"):
            payload["error"] = row["error"]
        if row.get("result"):
            try:
                payload["result"] = json.loads(row["result"])
            except (ValueError, TypeError):
                pass
        return payload

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        with self._lock:
            columns = [row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})")]
            if column not in columns:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                self._conn.commit()

    def save_backfill_batch(self, samples: list[dict[str, Any]]) -> int:
        """Tarihsel replay orneklerini (ozellik + madde + doldurulmus outcome) toplu yazar."""
        if not samples:
            return 0
        with self._lock, self._conn:
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO feature_snapshots
                  (run_id, coin, created_at, profile, feature_schema_version,
                   n_ok, n_partial, n_no_data, n_error, coverage_ratio, coverage_weighted,
                   weighted_score, signal_strength, score_mean, score_dispersion, confidence_mean,
                   category_scores, atr_pct, regime, volatility_bucket, current_price,
                   up_probability, down_probability, expected_low, expected_high, items_hash, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        sample["run_id"], sample["coin"], sample["created_at"],
                        sample.get("profile", "balanced"), 1,
                        sample.get("n_ok", 0), sample.get("n_partial", 0),
                        sample.get("n_no_data", 0), sample.get("n_error", 0),
                        sample.get("coverage_ratio"), sample.get("coverage_weighted"),
                        sample.get("weighted_score"), sample.get("signal_strength"),
                        sample.get("score_mean"), sample.get("score_dispersion"),
                        sample.get("confidence_mean"), sample.get("category_scores"),
                        sample.get("atr_pct"), sample.get("regime"), sample.get("volatility_bucket"),
                        sample.get("current_price"), sample.get("up_probability"),
                        sample.get("down_probability"), sample.get("expected_low"),
                        sample.get("expected_high"), sample.get("items_hash", "backfill"),
                        "backfill",
                    )
                    for sample in samples
                ],
            )
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO item_features
                  (run_id, item_id, coin, category, source, weight, score, confidence, status, contribution)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [tuple(item) for sample in samples for item in sample["items"]],
            )
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO outcomes
                  (run_id, horizon_days, coin, symbol, entry_price, entry_at, target_date, due_at,
                   exit_price, return_pct, hit, direction_at_run, weighted_score, price_source,
                   status, attempts, filled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'backfill', 'filled', 1, ?)
                """,
                [tuple(outcome) for sample in samples for outcome in sample["outcomes"]],
            )
        return len(samples)

    def executemany(self, sql: str, rows: list[tuple]) -> int:
        with self._lock, self._conn:
            cursor = self._conn.executemany(sql, rows)
            return cursor.rowcount or 0

    # ------------------------------------------------------------------ ogrenme dongusu
    def save_learning_run(
        self,
        features: dict[str, Any],
        items: list[dict[str, Any]],
        outcomes: list[dict[str, Any]],
    ) -> None:
        """Ozellik anlik goruntusu + madde izleri + bekleyen outcome satirlarini tek transactionda yazar."""
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO feature_snapshots
                  (run_id, coin, created_at, profile, feature_schema_version,
                   n_ok, n_partial, n_no_data, n_error, coverage_ratio, coverage_weighted,
                   weighted_score, signal_strength, score_mean, score_dispersion, confidence_mean,
                   category_scores, atr_pct, regime, volatility_bucket, current_price,
                   up_probability, down_probability, expected_low, expected_high, items_hash, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    features["run_id"], features["coin"], features["created_at"],
                    features.get("profile", "balanced"), features.get("feature_schema_version", 1),
                    features.get("n_ok", 0), features.get("n_partial", 0),
                    features.get("n_no_data", 0), features.get("n_error", 0),
                    features.get("coverage_ratio"), features.get("coverage_weighted"),
                    features.get("weighted_score"), features.get("signal_strength"),
                    features.get("score_mean"), features.get("score_dispersion"),
                    features.get("confidence_mean"), features.get("category_scores"),
                    features.get("atr_pct"), features.get("regime"), features.get("volatility_bucket"),
                    features.get("current_price"), features.get("up_probability"),
                    features.get("down_probability"), features.get("expected_low"),
                    features.get("expected_high"), features.get("items_hash"),
                    features.get("source", "live"),
                ),
            )
            self._conn.execute("DELETE FROM item_features WHERE run_id = ?", (features["run_id"],))
            self._conn.executemany(
                """
                INSERT INTO item_features
                  (run_id, item_id, coin, category, source, weight, score, confidence, status, contribution)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item["run_id"], item["item_id"], item["coin"], item.get("category"),
                        item.get("source"), item.get("weight"), item.get("score"),
                        item.get("confidence", 0.0), item.get("status", "no_data"),
                        item.get("contribution"),
                    )
                    for item in items
                ],
            )
            self._conn.executemany(
                """
                INSERT OR IGNORE INTO outcomes
                  (run_id, horizon_days, coin, symbol, entry_price, entry_at, target_date, due_at,
                   direction_at_run, weighted_score, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                [
                    (
                        outcome["run_id"], outcome["horizon_days"], outcome["coin"],
                        outcome.get("symbol"), outcome.get("entry_price"), outcome["entry_at"],
                        outcome["target_date"], outcome["due_at"], outcome.get("direction_at_run"),
                        outcome.get("weighted_score"),
                    )
                    for outcome in outcomes
                ],
            )

    def runs_missing_features(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.query(
            """
            SELECT r.run_id, r.coin, r.created_at, r.payload
            FROM runs r LEFT JOIN feature_snapshots f ON f.run_id = r.run_id
            WHERE f.run_id IS NULL
            ORDER BY r.created_at ASC LIMIT ?
            """,
            (limit,),
        )

    def learning_status_counts(self) -> dict[str, Any]:
        runs_total = self.query("SELECT COUNT(*) AS n FROM runs")[0]["n"]
        runs_with = self.query("SELECT COUNT(*) AS n FROM feature_snapshots")[0]["n"]
        rows = self.query("SELECT status, COUNT(*) AS n FROM outcomes GROUP BY status")
        outcomes = {row["status"]: row["n"] for row in rows}
        return {"runs_total": runs_total, "runs_with_features": runs_with, "outcomes": outcomes}

    def outcomes_due(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.query(
            """
            SELECT * FROM outcomes
            WHERE status = 'pending' AND due_at <= ?
            ORDER BY due_at ASC LIMIT ?
            """,
            (time.time(), limit),
        )

    def outcome_mark_filled(
        self,
        run_id: str,
        horizon_days: int,
        *,
        exit_price: float | None,
        return_pct: float | None,
        hit: int | None,
        price_source: str | None,
        note: str | None = None,
    ) -> None:
        self.execute(
            """
            UPDATE outcomes SET
              exit_price = ?, return_pct = ?, hit = ?, price_source = ?, note = ?,
              status = 'filled', attempts = attempts + 1, last_attempt_at = ?, filled_at = ?
            WHERE run_id = ? AND horizon_days = ?
            """,
            (
                exit_price, return_pct, hit, price_source, note,
                time.time(), time.time(), run_id, horizon_days,
            ),
        )

    def outcome_mark_failure(self, run_id: str, horizon_days: int, status: str, note: str) -> None:
        self.execute(
            """
            UPDATE outcomes SET status = ?, attempts = attempts + 1, last_attempt_at = ?, note = ?
            WHERE run_id = ? AND horizon_days = ?
            """,
            (status, time.time(), note, run_id, horizon_days),
        )

    def outcomes_dataset(self, horizon_days: int, coin: str | None = None) -> list[dict[str, Any]]:
        if coin:
            return self.query(
                """
                SELECT o.*, f.weighted_score AS f_score, f.up_probability AS f_up, f.coverage_ratio
                FROM outcomes o JOIN feature_snapshots f ON f.run_id = o.run_id
                WHERE o.horizon_days = ? AND o.status = 'filled' AND o.coin = ?
                ORDER BY o.target_date ASC
                """,
                (horizon_days, coin),
            )
        return self.query(
            """
            SELECT o.*, f.weighted_score AS f_score, f.up_probability AS f_up, f.coverage_ratio
            FROM outcomes o JOIN feature_snapshots f ON f.run_id = o.run_id
            WHERE o.horizon_days = ? AND o.status = 'filled'
            ORDER BY o.target_date ASC
            """,
            (horizon_days,),
        )

    def scheduled_job_acquire(self, job_key: str, lease_seconds: float) -> bool:
        now = time.time()
        with self._lock, self._conn:
            cursor = self._conn.execute(
                """
                UPDATE scheduled_jobs
                SET lease_until = ?, last_started_at = ?
                WHERE job_key = ? AND (lease_until IS NULL OR lease_until < ?)
                """,
                (now + lease_seconds, now, job_key, now),
            )
            if cursor.rowcount == 0:
                self._conn.execute(
                    "INSERT OR IGNORE INTO scheduled_jobs (job_key, lease_until, last_started_at) VALUES (?, ?, ?)",
                    (job_key, now + lease_seconds, now),
                )
                cursor = self._conn.execute(
                    "UPDATE scheduled_jobs SET lease_until = ?, last_started_at = ? WHERE job_key = ?",
                    (now + lease_seconds, now, job_key),
                )
            return cursor.rowcount > 0

    def scheduled_job_finish(self, job_key: str, status: str, error: str | None = None) -> None:
        self.execute(
            """
            UPDATE scheduled_jobs
            SET lease_until = NULL, last_finished_at = ?, last_status = ?, last_error = ?,
                run_count = run_count + 1
            WHERE job_key = ?
            """,
            (time.time(), status, error, job_key),
        )

    def feature_predictions(self, run_id: str) -> list[dict[str, Any]]:
        return self.query("SELECT * FROM predictions WHERE run_id = ?", (run_id,))

    def prediction_save(self, payload: dict[str, Any]) -> None:
        self.execute(
            """
            INSERT OR REPLACE INTO predictions
              (run_id, horizon_days, model_id, heuristic_up, probability_up, probability_down,
               n_train, calibration_n, calibration_observed, is_shadow, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["run_id"], payload["horizon_days"], payload["model_id"],
                payload.get("heuristic_up"), payload["probability_up"], payload["probability_down"],
                payload.get("n_train"), payload.get("calibration_n"),
                payload.get("calibration_observed"), 1 if payload.get("is_shadow", True) else 0,
                time.time(),
            ),
        )

    def learning_rows(
        self,
        horizon_days: int,
        coin: str | None = None,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        """Egitim veri seti: ozellik anlik goruntusu + doldurulmus outcome."""
        conditions = ["o.horizon_days = ?", "o.status = 'filled'", "o.return_pct IS NOT NULL"]
        params: list[Any] = [horizon_days]
        if coin:
            conditions.append("o.coin = ?")
            params.append(coin)
        if source:
            conditions.append("COALESCE(f.source, 'live') = ?")
            params.append(source)
        where = " AND ".join(conditions)
        return self.query(
            f"""
            SELECT o.run_id, o.coin, o.target_date, o.entry_at, o.return_pct, o.hit,
                   o.direction_at_run, o.weighted_score AS outcome_score,
                   f.created_at, f.profile, f.weighted_score, f.signal_strength,
                   f.coverage_ratio, f.coverage_weighted, f.score_mean, f.score_dispersion,
                   f.confidence_mean, f.category_scores, f.atr_pct, f.regime,
                   f.volatility_bucket, f.n_ok, f.n_partial, f.n_no_data, f.n_error,
                   COALESCE(f.source, 'live') AS source
            FROM outcomes o JOIN feature_snapshots f ON f.run_id = o.run_id
            WHERE {where}
            ORDER BY o.target_date ASC
            """,
            tuple(params),
        )

    def model_list(self) -> list[dict[str, Any]]:
        return self.query("SELECT * FROM model_registry ORDER BY trained_at DESC")

    def model_get(self, horizon_days: int, *, statuses: tuple[str, ...] = ("active", "shadow")) -> dict[str, Any] | None:
        placeholders = ",".join("?" for _ in statuses)
        rows = self.query(
            f"""
            SELECT * FROM model_registry
            WHERE horizon_days = ? AND status IN ({placeholders})
            ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, trained_at DESC LIMIT 1
            """,
            (horizon_days, *statuses),
        )
        return rows[0] if rows else None

    def model_save(self, payload: dict[str, Any]) -> None:
        self.execute(
            """
            INSERT OR REPLACE INTO model_registry
              (model_id, kind, horizon_days, status, trained_at, train_rows,
               feature_schema_version, params, metrics, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["model_id"], payload["kind"], payload["horizon_days"], payload["status"],
                payload.get("trained_at"), payload.get("train_rows"),
                payload.get("feature_schema_version", 1),
                payload.get("params"), payload.get("metrics"), payload.get("notes"),
            ),
        )

    def model_set_status(self, model_id: str, status: str) -> None:
        self.execute("UPDATE model_registry SET status = ? WHERE model_id = ?", (status, model_id))

    def calibration_bins_save(self, model_id: str, horizon_days: int, bins: list[dict[str, Any]]) -> None:
        self.execute("DELETE FROM calibration_bins WHERE model_id = ? AND horizon_days = ?", (model_id, horizon_days))
        self.executemany(
            """
            INSERT INTO calibration_bins
              (model_id, horizon_days, bin_index, bin_low, bin_high, n, predicted_mean,
               observed_rate, ci_low, ci_high, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    model_id, horizon_days, bucket["bin_index"], bucket["bin_low"],
                    bucket["bin_high"], bucket.get("n", 0), bucket.get("predicted_mean"),
                    bucket.get("observed_rate"), bucket.get("ci_low"), bucket.get("ci_high"),
                    time.time(),
                )
                for bucket in bins
            ],
        )

    def predictions_for_run(self, run_id: str) -> list[dict[str, Any]]:
        return self.query("SELECT * FROM predictions WHERE run_id = ?", (run_id,))

    def latest_feature_snapshot(self, coin: str) -> dict[str, Any] | None:
        rows = self.query(
            "SELECT * FROM feature_snapshots WHERE coin = ? ORDER BY created_at DESC LIMIT 1",
            (coin,),
        )
        return rows[0] if rows else None

    def feature_snapshots_for_coin(self, coin: str, limit: int = 200) -> list[dict[str, Any]]:
        return self.query(
            "SELECT * FROM feature_snapshots WHERE coin = ? ORDER BY created_at DESC LIMIT ?",
            (coin, limit),
        )

    DEFAULT_WATCHLIST: tuple[tuple[str, str, str], ...] = (
        ("bitcoin", "BTC", "Bitcoin"),
        ("ethereum", "ETH", "Ethereum"),
        ("solana", "SOL", "Solana"),
        ("binancecoin", "BNB", "BNB"),
        ("ripple", "XRP", "XRP"),
        ("cardano", "ADA", "Cardano"),
        ("dogecoin", "DOGE", "Dogecoin"),
        ("chainlink", "LINK", "Chainlink"),
        ("avalanche-2", "AVAX", "Avalanche"),
        ("polkadot", "DOT", "Polkadot"),
    )

    def seed_watchlist(self, *, only_if_empty: bool = True) -> int:
        """Veri birikimini hizlandirmak icin onerilen coinleri takibe ekler (idempotent)."""
        if only_if_empty and self.query("SELECT 1 FROM watchlist LIMIT 1"):
            return 0
        added = 0
        for coin, symbol, name in self.DEFAULT_WATCHLIST:
            exists = self.query("SELECT 1 FROM watchlist WHERE coin = ? LIMIT 1", (coin,))
            if exists:
                continue
            self.execute(
                """
                INSERT OR IGNORE INTO watchlist
                  (coin, symbol, name, profile, timeframe, auto_run, added_at)
                VALUES (?, ?, ?, 'balanced', '1d', 1, ?)
                """,
                (coin, symbol, name, time.time()),
            )
            added += 1
        return added

    def drift_save(self, entries: list[dict[str, Any]]) -> None:
        self.executemany(
            """
            INSERT INTO drift_metrics
              (computed_at, window_label, metric, scope, value, baseline, delta, psi, n,
               alarm, threshold, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    entry["computed_at"], entry["window_label"], entry["metric"],
                    entry.get("scope", "global"), entry.get("value"), entry.get("baseline"),
                    entry.get("delta"), entry.get("psi"), entry.get("n"),
                    1 if entry.get("alarm") else 0, entry.get("threshold"),
                    _dumps(entry.get("details")) if entry.get("details") is not None else None,
                )
                for entry in entries
            ],
        )

    def drift_latest(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.query(
            """
            SELECT * FROM drift_metrics
            WHERE computed_at = (SELECT MAX(computed_at) FROM drift_metrics)
            ORDER BY metric LIMIT ?
            """,
            (limit,),
        )

    def feature_scores_between(self, start: float, end: float) -> list[float]:
        rows = self.query(
            "SELECT weighted_score AS value FROM feature_snapshots WHERE created_at >= ? AND created_at < ?",
            (start, end),
        )
        return [float(row["value"]) for row in rows if row["value"] is not None]

    def coverage_between(self, start: float, end: float) -> tuple[int, float | None]:
        rows = self.query(
            "SELECT coverage_ratio AS value FROM feature_snapshots WHERE created_at >= ? AND created_at < ?",
            (start, end),
        )
        values = [float(row["value"]) for row in rows if row["value"] is not None]
        return len(values), (sum(values) / len(values) if values else None)

    def runs_to_archive(self, cutoff: float) -> list[dict[str, Any]]:
        return self.query(
            "SELECT run_id, coin, created_at, payload FROM runs WHERE created_at < ? ORDER BY created_at",
            (cutoff,),
        )

    def reports_to_archive(self, cutoff: float) -> list[dict[str, Any]]:
        return self.query(
            "SELECT * FROM reports WHERE created_at < ? ORDER BY created_at",
            (cutoff,),
        )

    def delete_runs(self, run_ids: list[str]) -> int:
        if not run_ids:
            return 0
        placeholders = ",".join("?" for _ in run_ids)
        return self.execute(f"DELETE FROM runs WHERE run_id IN ({placeholders})", run_ids).rowcount

    def delete_reports(self, names: list[str]) -> int:
        if not names:
            return 0
        placeholders = ",".join("?" for _ in names)
        return self.execute(f"DELETE FROM reports WHERE name IN ({placeholders})", names).rowcount

    def job_mark_stale(self) -> int:
        """Sunucu yeniden baslarken yarim kalan isleri hata olarak isaretler."""
        rows = self.query("SELECT id FROM jobs WHERE status IN ('queued', 'running')")
        for row in rows:
            self.execute(
                "UPDATE jobs SET status = 'error', error = ?, finished_at = ? WHERE id = ?",
                ("Sunucu yeniden başlatıldı; araştırma tamamlanamadı.", time.time(), row["id"]),
            )
        return len(rows)

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
