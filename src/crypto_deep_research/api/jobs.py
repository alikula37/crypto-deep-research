"""Arka plan is yoneticisi (uzun suren derin arastirmalar icin)."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

JobRunner = Callable[["Job"], Awaitable[dict[str, Any]]]
JobPersist = Callable[[dict[str, Any]], None]


@dataclass
class Job:
    id: str
    status: str = "queued"  # queued | running | done | error
    progress: int = 0
    message: str = "Sıraya alındı"
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    _persist: JobPersist | None = field(default=None, repr=False)

    def update(self, progress: int, message: str) -> None:
        self.progress = max(0, min(100, int(progress)))
        self.message = message
        self._notify(include_result=False)

    def _notify(self, *, include_result: bool) -> None:
        if self._persist is None:
            return
        try:
            self._persist(self.to_dict(include_result=include_result))
        except Exception:  # kalicilik hatasi isi durdurmasin
            logger.warning("Is durumu kaydedilemedi: %s", self.id)

    def to_dict(self, include_result: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": self.id,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }
        if self.error:
            payload["error"] = self.error
        if include_result and self.result is not None:
            payload["result"] = self.result
        return payload


class JobManager:
    """Bellek ici is kuyrugu; opsiyonel olarak SQLite'a yaz-through yapar."""

    def __init__(self, persist: JobPersist | None = None) -> None:
        self._jobs: dict[str, Job] = {}
        self._persist = persist

    def create(self, runner: JobRunner) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], _persist=self._persist)
        self._jobs[job.id] = job
        job._notify(include_result=False)
        asyncio.create_task(self._execute(job, runner))
        return job

    async def _execute(self, job: Job, runner: JobRunner) -> None:
        job.status = "running"
        job.message = "Başlatılıyor…"
        job._notify(include_result=False)
        try:
            job.result = await runner(job)
            job.status = "done"
            job.progress = 100
            job.message = "Tamamlandı"
        except asyncio.CancelledError:
            job.status = "error"
            job.error = "Görev iptal edildi."
        except Exception as exc:  # savunmaci: arka plan hatasi API'yi dusurmesin
            job.status = "error"
            job.error = str(exc)
        finally:
            job.finished_at = time.time()
            job._notify(include_result=True)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def has_running(self) -> bool:
        return any(job.status in ("queued", "running") for job in self._jobs.values())

    def prune(self, max_age_seconds: float = 3600.0) -> int:
        cutoff = time.time() - max_age_seconds
        stale = [
            job_id
            for job_id, job in self._jobs.items()
            if job.finished_at is not None and job.finished_at < cutoff
        ]
        for job_id in stale:
            self._jobs.pop(job_id, None)
        return len(stale)
