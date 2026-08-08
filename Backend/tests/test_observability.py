from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import ActivityEvent, WorkerHeartbeat
from app.observability.service import emit, heartbeat, purge_old_events, sanitize


def test_recursive_redaction_and_bounding():
    result = sanitize({"api_key": "secret", "nested": {"authorization": "bearer"},
                       "safe": "x" * 2000, "items": list(range(100))})
    assert result["api_key"] == "[REDACTED]"
    assert result["nested"]["authorization"] == "[REDACTED]"
    assert len(result["safe"]) == 1000
    assert len(result["items"]) == 50


def test_event_is_transactional_and_replay_ordered():
    engine = create_engine("sqlite://")
    ActivityEvent.__table__.create(engine)
    sessions = sessionmaker(bind=engine); db = sessions()
    emit(db, user_id="u", resource_type="run", resource_id="r", event_type="queued")
    db.rollback()
    assert db.query(ActivityEvent).count() == 0
    emit(db, user_id="u", resource_type="run", resource_id="r", event_type="queued"); db.commit()
    emit(db, user_id="u", resource_type="run", resource_id="r", event_type="started"); db.commit()
    assert [row.event_type for row in db.query(ActivityEvent).order_by(ActivityEvent.id)] == ["queued", "started"]


def test_retention_cleanup_is_bounded():
    engine = create_engine("sqlite://")
    ActivityEvent.__table__.create(engine); db = sessionmaker(bind=engine)()
    for index in range(3):
        row = ActivityEvent(user_id="u", resource_type="run", resource_id=str(index), event_type="completed",
                            payload={}, trace_id=str(index), created_at=datetime.now(timezone.utc)-timedelta(days=8))
        db.add(row)
    db.commit()
    assert purge_old_events(db, retention_days=7, limit=2) == 2
    assert db.query(ActivityEvent).count() == 1


def test_worker_heartbeat_upserts_one_instance():
    engine = create_engine("sqlite://")
    WorkerHeartbeat.__table__.create(engine); db = sessionmaker(bind=engine)()
    heartbeat(db, "ingestion", "one"); heartbeat(db, "ingestion", "one", status="offline")
    assert db.query(WorkerHeartbeat).count() == 1
    assert db.query(WorkerHeartbeat).one().status == "offline"
