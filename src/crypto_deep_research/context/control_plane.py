"""Context Control Plane.

Her context objesinin kimligi, scope'u, provenance'i, TTL'i ve versiyonu vardir.
Politika kararları: KEEP / COMPRESS / CACHE / OFFLOAD / DROP / PIN / PREFETCH.
Offload geri alınabilir: tam veri SQLite blob'unda tutulur, gerektiğinde rehydrate edilir.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Iterable
from typing import Any

from crypto_deep_research.config import Settings
from crypto_deep_research.models import (
    AnalysisResult,
    ContextObject,
    ItemResult,
    PolicyAction,
    ResearchRun,
    utcnow,
)
from crypto_deep_research.providers.base import estimate_tokens
from crypto_deep_research.storage.db import Database

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_BUDGET = 14000


def _content_hash(content: str) -> str:
    return hashlib.sha1(content.encode("utf-8")).hexdigest()


class ContextControlPlane:
    """Context lifecycle yönetimi: kayıt, politika, offload/compress/rehydrate."""

    def __init__(
        self,
        db: Database,
        settings: Settings,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
    ) -> None:
        self.db = db
        self.settings = settings
        self.token_budget = token_budget
        self._prefetched: dict[str, list[ContextObject]] = {}

    # ------------------------------------------------------------------ kayıt
    def register_analysis(self, coin_id: str, result: AnalysisResult) -> ContextObject:
        content = self._analysis_content(result)
        priority = 0.9 if result.status in {"ok", "partial"} else 0.3
        obj = ContextObject(
            key=f"analysis:{coin_id}:{result.key}",
            kind="analysis",
            scope={"coin": coin_id, "key": result.key},
            content=content,
            data=result.data,
            provenance=result.sources,
            ttl_seconds=6 * 3600,
            tokens_estimate=estimate_tokens(content),
            priority=priority,
        )
        self.db.save_context(obj)
        return obj

    def register_item(self, coin_id: str, item: ItemResult) -> ContextObject:
        content = (
            f"{item.item_id}. {item.title_tr}\nDurum: {item.status}\n{item.summary}\n"
            f"Skor: {item.score} (güven: {item.confidence})"
        )
        obj = ContextObject(
            key=f"item:{coin_id}:{item.item_id}",
            kind="research_item",
            scope={"coin": coin_id, "item": str(item.item_id)},
            content=content,
            data=item.data,
            provenance=item.sources,
            ttl_seconds=12 * 3600,
            tokens_estimate=estimate_tokens(content),
            priority=0.7,
        )
        self.db.save_context(obj)
        return obj

    def register_run(self, run: ResearchRun) -> ContextObject:
        content = self.render_run_summary(run)
        obj = ContextObject(
            key=f"run:{run.coin.id}:{run.run_id}",
            kind="report",
            scope={"coin": run.coin.id, "run": run.run_id},
            content=content,
            data={"run_id": run.run_id},
            provenance=run.sources,
            ttl_seconds=30 * 86400,
            tokens_estimate=estimate_tokens(content),
            priority=1.0,
            pinned=True,
        )
        self.db.save_context(obj)
        return obj

    # ------------------------------------------------------------------ politika
    def decide(self, obj: ContextObject, seen_hashes: set[str] | None = None) -> PolicyAction:
        now = time.time()
        age = now - obj.updated_at.timestamp()
        if obj.pinned:
            return "PIN"
        if obj.ttl_seconds and age > obj.ttl_seconds:
            return "DROP"
        if seen_hashes is not None and _content_hash(obj.content) in seen_hashes:
            return "DROP"
        if obj.tokens_estimate > 1200:
            return "COMPRESS"
        if obj.priority >= 0.85:
            return "KEEP"
        if obj.state == "offloaded":
            return "PREFETCH"
        return "CACHE"

    def apply_policy(
        self, objects: Iterable[ContextObject], token_budget: int | None = None
    ) -> dict[str, list[ContextObject]]:
        """Objeleri politika kararlarına göre gruplar."""
        budget = token_budget or self.token_budget
        groups: dict[str, list[ContextObject]] = {
            action: [] for action in ("PIN", "KEEP", "COMPRESS", "CACHE", "OFFLOAD", "DROP", "PREFETCH")
        }
        seen: set[str] = set()
        ordered = sorted(objects, key=lambda obj: obj.priority, reverse=True)
        used = 0
        for obj in ordered:
            action = self.decide(obj, seen)
            if action == "DROP":
                groups["DROP"].append(obj)
                continue
            if action in ("PIN", "KEEP", "CACHE"):
                if used + obj.tokens_estimate <= budget:
                    used += obj.tokens_estimate
                    groups[action].append(obj)
                else:
                    action = "COMPRESS"
            if action == "COMPRESS":
                compressed = self.compress(obj)
                if used + compressed.tokens_estimate <= budget:
                    used += compressed.tokens_estimate
                    groups["COMPRESS"].append(compressed)
                else:
                    groups["OFFLOAD"].append(self.offload(obj))
            seen.add(_content_hash(obj.content))
        return groups

    # ------------------------------------------------------------------ işlemler
    def compress(self, obj: ContextObject, max_chars: int = 600) -> ContextObject:
        if len(obj.content) <= max_chars:
            return obj
        truncated = obj.content[:max_chars].rsplit(" ", 1)[0] + "..."
        if obj.data:
            summary_bits = []
            for key in ("summary", "reasons", "sentiment_24h", "reasons"):
                value = obj.data.get(key)
                if value:
                    summary_bits.append(f"{key}={json.dumps(value, ensure_ascii=False, default=str)[:200]}")
            if summary_bits:
                truncated += " | " + " ; ".join(summary_bits)
        compressed = obj.model_copy(
            update={
                "content": truncated,
                "tokens_estimate": estimate_tokens(truncated),
                "state": "compressed",
                "updated_at": utcnow(),
            }
        )
        self.db.save_context(compressed)
        return compressed

    def offload(self, obj: ContextObject) -> ContextObject:
        blob_key = f"blob:{obj.key}"
        self.db.save_blob(blob_key, {"content": obj.content, "data": obj.data})
        preview = obj.content[:240].rsplit(" ", 1)[0] + "..." if len(obj.content) > 240 else obj.content
        offloaded = obj.model_copy(
            update={
                "content": preview,
                "blob_ref": blob_key,
                "state": "offloaded",
                "tokens_estimate": estimate_tokens(preview),
                "updated_at": utcnow(),
            }
        )
        self.db.save_context(offloaded)
        return offloaded

    def rehydrate(self, key: str) -> ContextObject | None:
        obj = self.db.get_context(key)
        if obj is None:
            return None
        if obj.blob_ref:
            blob = self.db.get_blob(obj.blob_ref)
            if blob:
                obj = obj.model_copy(
                    update={
                        "content": blob.get("content", obj.content),
                        "data": blob.get("data", obj.data),
                        "state": "hot",
                        "tokens_estimate": estimate_tokens(blob.get("content", "")),
                    }
                )
                self.db.save_context(obj)
        return obj

    # ------------------------------------------------------------------ materialize
    def materialize(
        self, objects: Iterable[ContextObject], token_budget: int | None = None
    ) -> tuple[str, dict[str, Any]]:
        """Politika uygulanmis context'i promptlanabilir metne cevirir."""
        groups = self.apply_policy(objects, token_budget)
        parts: list[str] = []
        for action in ("PIN", "KEEP", "COMPRESS", "CACHE"):
            for obj in groups[action]:
                tag = "ÖNEMLİ" if action in ("PIN", "KEEP") else "ÖZET"
                parts.append(f"[{tag}] {obj.content}")
        if groups["OFFLOAD"]:
            parts.append(
                "[ARSIV] "
                + ", ".join(obj.key for obj in groups["OFFLOAD"])
                + " (detaylar saklandi, gerekirse istenebilir)"
            )
        text = "\n\n".join(parts)
        stats = {
            "groups": {action: len(objs) for action, objs in groups.items()},
            "tokens": estimate_tokens(text),
            "budget": token_budget or self.token_budget,
        }
        return text, stats

    # ------------------------------------------------------------------ prefetch
    def mark_prefetch(self, keys: list[str]) -> list[ContextObject]:
        """Sik kullanılacak tahmin edilen context'leri önceden yükler."""
        loaded = []
        for key in keys:
            obj = self.rehydrate(key) or self.db.get_context(key)
            if obj:
                self._prefetched.setdefault(obj.kind, []).append(obj)
                loaded.append(obj)
        return loaded

    def prefetched(self, kind: str) -> list[ContextObject]:
        return self._prefetched.get(kind, [])

    # ------------------------------------------------------------------ ic yardımcilar
    @staticmethod
    def _analysis_content(result: AnalysisResult) -> str:
        lines = [
            f"## {result.title} [{result.status}]",
            result.summary,
        ]
        if result.data.get("reasons"):
            lines.append("Nedenler: " + "; ".join(str(r) for r in result.data["reasons"][:8]))
        if result.sources:
            lines.append(
                "Kaynaklar: "
                + ", ".join(sorted({source.name for source in result.sources}))
            )
        return "\n".join(lines)

    @staticmethod
    def render_run_summary(run: ResearchRun) -> str:
        lines = [
            f"Kosu {run.run_id} - {run.coin.name} ({run.coin.symbol.upper()})",
            f"Tarih: {run.created_at.isoformat()}",
            f"Fiyat: ${run.current_price:,.6g}" if run.current_price else "",
            f"Ağırlıklı skor: {run.weighted_score}",
            f"Yükseliş olasılığı: %{run.up_probability}" if run.up_probability else "",
            f"Beklenen aralık: {run.expected_low} - {run.expected_high}",
        ]
        return "\n".join(line for line in lines if line)
