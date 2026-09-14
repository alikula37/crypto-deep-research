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


async def test_job_persistence_roundtrip(tmp_path):
    from crypto_deep_research.storage.db import Database

    db = Database(tmp_path / "t.db")
    manager = JobManager(persist=db.job_save)

    async def runner(job):
        job.update(50, "yarı")
        return {"ok": True}

    job = manager.create(runner)
    await _wait(job)
    stored = db.job_get(job.id)
    assert stored["status"] == "done"
    assert stored["result"] == {"ok": True}
    assert stored["progress"] == 100
    assert stored["finished_at"] is not None
    assert db.job_get("yok") is None


def test_job_mark_stale_flags_interrupted_runs(tmp_path):
    from crypto_deep_research.storage.db import Database

    db = Database(tmp_path / "t.db")
    db.job_save(
        {
            "job_id": "x1",
            "status": "running",
            "progress": 40,
            "message": "calisiyor",
            "created_at": 1.0,
        }
    )
    db.job_save({"job_id": "x2", "status": "done", "progress": 100, "created_at": 1.0})
    assert db.job_mark_stale() == 1
    interrupted = db.job_get("x1")
    assert interrupted["status"] == "error"
    assert "yeniden başlatıldı" in interrupted["error"]
    assert db.job_get("x2")["status"] == "done"
