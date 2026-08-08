import asyncio
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.core.config import settings
from app.db.models import ActivityEvent, WorkerHeartbeat
from app.db.session import SessionLocal, get_db

router = APIRouter(tags=["observability"])
_connections: dict[str, int] = defaultdict(int)
_reconnects = 0


def event_out(row: ActivityEvent) -> dict:
    return {"id": row.id, "resource_type": row.resource_type, "resource_id": row.resource_id,
            "event_type": row.event_type, "payload": row.payload, "trace_id": row.trace_id,
            "correlation_id": row.correlation_id, "created_at": row.created_at.isoformat()}


def query_events(db: Session, user_id: str, after: int, resource_type: str | None,
                 resource_id: str | None, limit: int):
    query = db.query(ActivityEvent).filter(ActivityEvent.user_id == user_id, ActivityEvent.id > after)
    if resource_type: query = query.filter(ActivityEvent.resource_type == resource_type)
    if resource_id: query = query.filter(ActivityEvent.resource_id == resource_id)
    return query.order_by(ActivityEvent.id).limit(limit).all()


@router.get("/events")
def list_events(after: int = 0, resource_type: str | None = None, resource_id: str | None = None,
                limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
                user_id: str = Depends(get_current_user_id)):
    rows = query_events(db, user_id, after, resource_type, resource_id, limit)
    return {"items": [event_out(row) for row in rows], "next_cursor": rows[-1].id if rows else after}


@router.get("/events/stream")
async def stream_events(request: Request, after: int = 0, resource_type: str | None = None,
                        resource_id: str | None = None,
                        last_event_id: str | None = Header(None, alias="Last-Event-ID"),
                        user_id: str = Depends(get_current_user_id)):
    global _reconnects
    if _connections[user_id] >= settings.sse_max_connections_per_tenant:
        raise HTTPException(status_code=429, detail="Too many event streams for this tenant")
    cursor = max(after, int(last_event_id or 0)); _connections[user_id] += 1
    if cursor: _reconnects += 1

    async def generate():
        nonlocal cursor
        heartbeat_at = asyncio.get_running_loop().time(); expires = heartbeat_at + settings.sse_max_duration_seconds
        try:
            while asyncio.get_running_loop().time() < expires and not await request.is_disconnected():
                db = SessionLocal()
                try: rows = query_events(db, user_id, cursor, resource_type, resource_id, settings.event_batch_size)
                finally: db.close()
                if rows:
                    for row in rows:
                        cursor = row.id
                        yield f"id: {row.id}\nevent: {row.event_type}\ndata: {json.dumps(event_out(row), separators=(',', ':'))}\n\n"
                    heartbeat_at = asyncio.get_running_loop().time()
                    continue
                now = asyncio.get_running_loop().time()
                if now - heartbeat_at >= 15:
                    yield ": heartbeat\n\n"; heartbeat_at = now
                await asyncio.sleep(settings.event_poll_seconds)
        finally:
            _connections[user_id] = max(0, _connections[user_id] - 1)

    return StreamingResponse(generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


def worker_out(row: WorkerHeartbeat) -> dict:
    age = max(0, (datetime.now(timezone.utc) - row.last_seen_at).total_seconds())
    stale = age > settings.worker_heartbeat_seconds * 3
    return {"id": row.id, "worker_type": row.worker_type, "instance_id": row.instance_id,
            "status": "stale" if stale else row.status, "last_seen_at": row.last_seen_at,
            "heartbeat_age_seconds": round(age, 1), "metadata": row.metadata_json}


@router.get("/operations/workers")
def workers(db: Session = Depends(get_db), _: str = Depends(get_current_user_id)):
    return [worker_out(row) for row in db.query(WorkerHeartbeat).order_by(WorkerHeartbeat.worker_type).all()]


@router.get("/operations/summary")
def operations_summary(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    queues = {}
    for name, table in (("ingestion", "ingestion_job"), ("indexing", "indexing_job"),
                        ("evaluation", "evaluation_run"), ("workflow", "workflow_job")):
        row = db.execute(text(f"""select count(*) filter(where status in ('queued','retry_wait')) depth,
          coalesce(extract(epoch from(now()-min(created_at) filter(where status in ('queued','retry_wait')))),0) oldest,
          count(*) filter(where status='failed') failed from {table} where user_id=:user_id"""),
                         {"user_id": user_id}).mappings().one()
        oldest = float(row["oldest"]); health = "critical" if oldest >= 300 else "warning" if oldest >= 60 else "healthy"
        queues[name] = {"depth": row["depth"], "oldest_seconds": round(oldest, 1),
                        "failed": row["failed"], "health": health}
    since = datetime.now(timezone.utc) - timedelta(minutes=15)
    failures = db.query(ActivityEvent).filter(ActivityEvent.user_id == user_id,
        ActivityEvent.event_type.in_(["failed", "retrying"]), ActivityEvent.created_at >= since).count()
    workers_data = [worker_out(row) for row in db.query(WorkerHeartbeat).all()]
    overall = "critical" if any(q["health"] == "critical" for q in queues.values()) or any(
        w["status"] == "stale" for w in workers_data) or failures >= 10 else "warning" if any(
        q["health"] == "warning" for q in queues.values()) or failures >= 3 else "healthy"
    return {"health": overall, "queues": queues, "recent_failures": failures,
            "workers": workers_data, "generated_at": datetime.now(timezone.utc)}


def sse_metrics():
    return sum(_connections.values()), _reconnects
