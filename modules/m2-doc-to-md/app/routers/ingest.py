import asyncio
import uuid

from fastapi import APIRouter, BackgroundTasks

from app.pipeline.run import run as pipeline_run

router = APIRouter()

_jobs: dict[str, dict] = {}


@router.post("/ingest/scan")
async def scan(bg: BackgroundTasks):
    jid = uuid.uuid4().hex
    _jobs[jid] = {"status": "running", "started": True}

    def _wrap():
        try:
            pipeline_run()
            _jobs[jid]["status"] = "done"
        except Exception as e:
            _jobs[jid]["status"] = f"error:{e}"

    bg.add_task(_wrap)
    return {"job_id": jid, "status": "queued"}


@router.get("/ingest/status/{jid}")
async def status(jid: str):
    return _jobs.get(jid, {"status": "unknown"})
