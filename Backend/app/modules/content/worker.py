import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import ContentItem, IndexingJob, IngestionJob
from app.modules.content.domain import IngestionFailure
from app.modules.content.parsers import DocumentParserFactory
from app.modules.content.ports import ObjectStoragePort
from app.observability.service import emit, maybe_heartbeat

logger = logging.getLogger("agent_studio.ingestion")


class IngestionWorker:
    def __init__(self, session_factory, storage: ObjectStoragePort, *, lease_seconds: int = 120) -> None:
        self.session_factory = session_factory
        self.storage = storage
        self.parsers = DocumentParserFactory()
        self.lease_seconds = lease_seconds
        self.worker_id = str(uuid.uuid4())

    def run_once(self) -> bool:
        session = self.session_factory()
        try:
            maybe_heartbeat(self, session, "ingestion")
            job = self._claim(session)
            if not job:
                return False
            content_id = job.content_id
        finally:
            session.close()
        self._process(content_id)
        return True

    def _claim(self, session: Session) -> IngestionJob | None:
        now = datetime.now(timezone.utc)
        job = (session.query(IngestionJob)
               .filter(IngestionJob.available_at <= now,
                       or_(IngestionJob.status.in_(["queued", "retry_wait"]),
                           (IngestionJob.status == "running") & (IngestionJob.lease_until < now)))
               .order_by(IngestionJob.available_at, IngestionJob.created_at)
               .with_for_update(skip_locked=True).first())
        if not job:
            session.rollback()
            return None
        job.status = "running"
        job.attempt_count += 1
        job.lease_owner = self.worker_id
        job.lease_until = now + timedelta(seconds=self.lease_seconds)
        job.updated_at = now
        item = session.query(ContentItem).filter(ContentItem.id == job.content_id).first()
        if item:
            item.status = "processing"
            item.updated_at = now
            emit(session, user_id=item.user_id, resource_type="ingestion", resource_id=item.id,
                 event_type="started", payload={"attempt": job.attempt_count})
        session.commit()
        return job

    def _process(self, content_id: str) -> None:
        session = self.session_factory()
        try:
            item = session.query(ContentItem).filter(ContentItem.id == content_id).first()
            if not item:
                return
            try:
                raw = self.storage.download(item.storage_path)
                parsed = self.parsers.create(item.mime_type or "").parse(raw)
            except IngestionFailure as exc:
                self._fail(session, item, exc)
                return
            except Exception:
                self._fail(session, item, IngestionFailure(
                    "storage_unavailable", "Document storage is temporarily unavailable.", retryable=True))
                return
            job = session.query(IngestionJob).filter(IngestionJob.content_id == item.id).first()
            if not job or job.lease_owner != self.worker_id:
                return
            now = datetime.now(timezone.utc)
            item.extracted_text = parsed.text
            item.page_count = parsed.page_count
            item.character_count = parsed.character_count
            item.status = "ready"
            item.error_code = item.error_message = None
            item.index_status = "pending"
            item.index_error_code = item.index_error_message = None
            item.updated_at = now
            job.status = "succeeded"
            job.completed_at = now
            job.lease_owner = job.lease_until = None
            job.updated_at = now
            index_job = session.query(IndexingJob).filter(IndexingJob.content_id == item.id).first()
            if not index_job:
                index_job = IndexingJob(user_id=item.user_id, content_id=item.id, created_at=now, updated_at=now)
                session.add(index_job)
            index_job.status = "queued"
            index_job.attempt_count = 0
            index_job.available_at = now
            index_job.lease_owner = index_job.lease_until = None
            index_job.last_error_code = index_job.last_error_message = None
            index_job.completed_at = None
            index_job.updated_at = now
            emit(session, user_id=item.user_id, resource_type="ingestion", resource_id=item.id,
                 event_type="completed", payload={"page_count": item.page_count,
                                                   "character_count": item.character_count})
            emit(session, user_id=item.user_id, resource_type="indexing", resource_id=item.id,
                 event_type="queued", payload={})
            session.commit()
        finally:
            session.close()

    def _fail(self, session: Session, item: ContentItem, failure: IngestionFailure) -> None:
        job = session.query(IngestionJob).filter(IngestionJob.content_id == item.id).first()
        if not job or job.lease_owner != self.worker_id:
            return
        now = datetime.now(timezone.utc)
        if failure.retryable and job.attempt_count < job.max_attempts:
            delays = (5, 30, 120)
            job.status = "retry_wait"
            job.available_at = now + timedelta(seconds=delays[min(job.attempt_count - 1, 2)])
            item.status = "queued"
        else:
            job.status = "failed"
            job.completed_at = now
            item.status = "failed"
            item.index_status = "failed"
            item.index_error_code = "extraction_not_ready"
            item.index_error_message = "Text extraction must succeed before this document can be indexed."
        job.last_error_code = failure.code
        job.last_error_message = failure.message
        job.lease_owner = job.lease_until = None
        job.updated_at = now
        item.error_code = failure.code
        item.error_message = failure.message
        item.updated_at = now
        emit(session, user_id=item.user_id, resource_type="ingestion", resource_id=item.id,
             event_type="retrying" if job.status == "retry_wait" else "failed",
             payload={"code": failure.code, "attempt": job.attempt_count})
        session.commit()
