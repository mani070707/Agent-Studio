import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from app.db.models import ContentItem, DocumentChunk, IndexingJob
from app.modules.semantic.chunking import DeterministicChunker
from app.modules.semantic.domain import IndexFailure
from app.modules.semantic.ports import EmbeddingPort
from app.modules.semantic.metrics import semantic_metrics
from app.observability.service import emit, maybe_heartbeat


class IndexingWorker:
    def __init__(self, session_factory, embedder: EmbeddingPort, *, index_version: int = 1,
                 lease_seconds: int = 600, timeout_seconds: int = 300) -> None:
        self.session_factory = session_factory
        self.embedder = embedder
        self.chunker = DeterministicChunker(embedder)
        self.index_version = index_version
        self.lease_seconds = lease_seconds
        self.timeout_seconds = timeout_seconds
        self.worker_id = str(uuid.uuid4())

    def run_once(self) -> bool:
        session = self.session_factory()
        try:
            maybe_heartbeat(self, session, "indexing")
            now = datetime.now(timezone.utc)
            job = (session.query(IndexingJob)
                   .filter(IndexingJob.available_at <= now,
                           or_(IndexingJob.status.in_(["queued", "retry_wait"]),
                               (IndexingJob.status == "running") & (IndexingJob.lease_until < now)))
                   .order_by(IndexingJob.available_at, IndexingJob.created_at)
                   .with_for_update(skip_locked=True).first())
            if not job:
                session.rollback()
                return False
            job.status = "running"
            job.attempt_count += 1
            job.lease_owner = self.worker_id
            job.lease_until = now + timedelta(seconds=self.lease_seconds)
            job.updated_at = now
            item = session.query(ContentItem).filter(ContentItem.id == job.content_id).first()
            if item:
                item.index_status = "indexing"
                item.updated_at = now
                emit(session, user_id=item.user_id, resource_type="indexing", resource_id=item.id,
                     event_type="started", payload={"attempt": job.attempt_count})
            content_id = job.content_id
            session.commit()
        finally:
            session.close()
        self._process(content_id)
        return True

    def _process(self, content_id: str) -> None:
        started = time.monotonic()
        session = self.session_factory()
        try:
            item = session.query(ContentItem).filter(ContentItem.id == content_id).first()
            if not item:
                return
            if item.status != "ready":
                self._fail(session, item, IndexFailure(
                    "extraction_not_ready", "Text extraction must succeed before indexing."))
                return
            try:
                drafts = self.chunker.chunk(item.id, item.extracted_text, self.index_version)
                vectors = self.embedder.embed_documents([draft.text for draft in drafts])
                if time.monotonic() - started > self.timeout_seconds:
                    raise IndexFailure("indexing_timeout", "Document indexing exceeded its time limit.", retryable=True)
            except IndexFailure as exc:
                self._fail(session, item, exc)
                return
            job = session.query(IndexingJob).filter(IndexingJob.content_id == item.id).first()
            if not job or job.lease_owner != self.worker_id:
                return
            now = datetime.now(timezone.utc)
            session.query(DocumentChunk).filter(DocumentChunk.content_id == item.id).delete()
            session.add_all([
                DocumentChunk(id=draft.id, user_id=item.user_id, knowledge_base_id=item.knowledge_base_id,
                              content_id=item.id, ordinal=draft.ordinal, text=draft.text,
                              token_count=draft.token_count, page_start=draft.page_start,
                              page_end=draft.page_end, text_hash=draft.text_hash,
                              embedding_model=self.embedder.model_name, index_version=self.index_version,
                              embedding=vector, created_at=now)
                for draft, vector in zip(drafts, vectors, strict=True)
            ])
            item.index_status = "indexed"
            item.embedding_model = self.embedder.model_name
            item.index_version = self.index_version
            item.chunk_count = len(drafts)
            item.indexed_at = now
            item.index_error_code = item.index_error_message = None
            item.updated_at = now
            job.status = "succeeded"
            job.completed_at = now
            job.lease_owner = job.lease_until = None
            job.updated_at = now
            emit(session, user_id=item.user_id, resource_type="indexing", resource_id=item.id,
                 event_type="completed", payload={"chunk_count": len(drafts),
                                                   "duration_ms": round((time.monotonic()-started)*1000, 1)})
            session.commit()
            semantic_metrics.record_index(len(drafts), time.monotonic() - started)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _fail(self, session, item: ContentItem, failure: IndexFailure) -> None:
        job = session.query(IndexingJob).filter(IndexingJob.content_id == item.id).first()
        if not job or job.lease_owner != self.worker_id:
            return
        now = datetime.now(timezone.utc)
        if failure.retryable and job.attempt_count < job.max_attempts:
            delays = (5, 30, 120)
            job.status = "retry_wait"
            job.available_at = now + timedelta(seconds=delays[min(job.attempt_count - 1, 2)])
            item.index_status = "pending"
        else:
            job.status = "failed"
            job.completed_at = now
            item.index_status = "failed"
        job.last_error_code = failure.code
        job.last_error_message = failure.message
        job.lease_owner = job.lease_until = None
        job.updated_at = now
        item.index_error_code = failure.code
        item.index_error_message = failure.message
        item.updated_at = now
        emit(session, user_id=item.user_id, resource_type="indexing", resource_id=item.id,
             event_type="retrying" if job.status == "retry_wait" else "failed",
             payload={"code": failure.code, "attempt": job.attempt_count})
        session.commit()
        semantic_metrics.record_failure(failure.code)
