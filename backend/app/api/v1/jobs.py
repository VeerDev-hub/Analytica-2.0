import asyncio
import json
import uuid
from datetime import UTC, datetime

import redis.asyncio as aioredis
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.models import Job
from app.repositories.access import get_job
from app.schemas.common import JobOut
from app.services.jobs import TERMINAL, job_payload
from app.tasks.celery_app import celery_app

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def get(job_id: uuid.UUID, user: CurrentUser, db: DB) -> Job:
    return get_job(db, user, job_id)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel(job_id: uuid.UUID, user: CurrentUser, db: DB) -> Job:
    job = get_job(db, user, job_id)
    if job.status not in TERMINAL:
        job.status = "cancelled"
        job.message = "Cancelled"
        job.finished_at = datetime.now(UTC)
        db.commit()
        celery_app.control.revoke(str(job.id))
    return job


@router.get("/{job_id}/events")
async def events(job_id: uuid.UUID, user: CurrentUser, db: DB) -> StreamingResponse:
    """Server-Sent Events: current state first, then every progress update until terminal."""
    job = get_job(db, user, job_id)
    first = job_payload(job)

    async def stream():
        yield f"data: {json.dumps(first, default=str)}\n\n"
        if first["status"] in TERMINAL:
            return
        client = aioredis.from_url(get_settings().redis_url)
        pubsub = client.pubsub()
        await pubsub.subscribe(f"job:{job_id}")
        try:
            idle = 0
            while idle < 600:  # give up after ~10 minutes of silence
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg is None:
                    idle += 1
                    if idle % 15 == 0:
                        yield ": keep-alive\n\n"
                    await asyncio.sleep(0)
                    continue
                idle = 0
                data = msg["data"].decode() if isinstance(msg["data"], bytes) else msg["data"]
                yield f"data: {data}\n\n"
                if json.loads(data).get("status") in TERMINAL:
                    break
        finally:
            await pubsub.unsubscribe()
            await client.aclose()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
