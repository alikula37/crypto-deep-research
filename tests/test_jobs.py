"""Arka plan is yoneticisi testleri."""

from __future__ import annotations

import asyncio

from crypto_deep_research.api.jobs import JobManager


async def _wait(job, timeout: float = 2.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while job.status in ("queued", "running"):
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError("job tamamlanmadi")
        await asyncio.sleep(0.01)


async def test_job_manager_success():
    manager = JobManager()

    async def runner(job):
        job.update(50, "Yarısı tamam")
        return {"ok": True}

    job = manager.create(runner)
    await _wait(job)
    assert job.status == "done"
    assert job.progress == 100
    assert job.result == {"ok": True}
    payload = job.to_dict()
    assert payload["job_id"] == job.id
    assert payload["result"] == {"ok": True}


async def test_job_manager_error():
    manager = JobManager()

    async def runner(job):
        raise RuntimeError("veri kaynağı yanıt vermedi")

    job = manager.create(runner)
    await _wait(job)
    assert job.status == "error"
    assert "veri kaynağı" in (job.error or "")


async def test_job_manager_prune():
    manager = JobManager()

    async def runner(job):
        return {}

    job = manager.create(runner)
    await _wait(job)
    job.finished_at = 0.0
    assert manager.prune(max_age_seconds=1.0) == 1
    assert manager.get(job.id) is None
