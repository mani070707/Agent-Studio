import re
import uuid
import time
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from app.db.models import ActivityEvent, WorkerHeartbeat

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
SENSITIVE = re.compile(r"(secret|token|password|authorization|api[_-]?key|signed[_-]?url|prompt|document[_-]?text|embedding|message[_-]?text)", re.I)


def sanitize(value, key: str = ""):
    if SENSITIVE.search(key): return "[REDACTED]"
    if isinstance(value, dict): return {str(k): sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, list): return [sanitize(item) for item in value[:50]]
    if isinstance(value, str): return value[:1000]
    if value is None or isinstance(value, (bool, int, float)): return value
    return str(value)[:1000]


def emit(db: Session, *, user_id: str, resource_type: str, resource_id: str,
         event_type: str, payload: dict | None = None, trace_id: str | None = None,
         correlation_id: str | None = None) -> ActivityEvent:
    event = ActivityEvent(user_id=user_id, resource_type=resource_type, resource_id=resource_id,
        event_type=event_type, payload=sanitize(payload or {}), trace_id=trace_id or resource_id,
        correlation_id=correlation_id or correlation_id_var.get())
    db.add(event)
    return event


def heartbeat(db: Session, worker_type: str, instance_id: str, status: str = "online", metadata=None):
    key = f"{worker_type}:{instance_id}"; now = datetime.now(timezone.utc)
    row = db.query(WorkerHeartbeat).filter(WorkerHeartbeat.id == key).first()
    if row:
        row.status = status; row.last_seen_at = now; row.metadata_json = sanitize(metadata or {})
    else:
        row = WorkerHeartbeat(id=key, worker_type=worker_type, instance_id=instance_id,
            status=status, metadata_json=sanitize(metadata or {}), started_at=now, last_seen_at=now)
        db.add(row)
    db.commit(); return row


def maybe_heartbeat(worker, db: Session, worker_type: str, interval_seconds: int = 20):
    now = time.monotonic()
    if now - getattr(worker, "_heartbeat_at", 0) >= interval_seconds:
        heartbeat(db, worker_type, worker.worker_id)
        worker._heartbeat_at = now


def purge_old_events(db: Session, retention_days: int = 7, limit: int = 1000) -> int:
    ids = [row[0] for row in db.query(ActivityEvent.id).filter(
        ActivityEvent.created_at < datetime.now(timezone.utc) - timedelta(days=retention_days)
    ).order_by(ActivityEvent.id).limit(limit).all()]
    if ids:
        db.query(ActivityEvent).filter(ActivityEvent.id.in_(ids)).delete(synchronize_session=False); db.commit()
    return len(ids)


def new_correlation_id() -> str: return str(uuid.uuid4())
