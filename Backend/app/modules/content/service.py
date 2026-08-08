import hashlib
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import ContentItem, IngestionJob
from app.modules.content.domain import ContentStatus, IngestionFailure
from app.modules.content.parsers import detect_document_type
from app.modules.content.ports import ObjectStoragePort
from app.modules.knowledge.application import KnowledgeBaseService
from app.observability.service import emit

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class ContentNotFound(LookupError):
    pass


class DuplicateContent(ValueError):
    def __init__(self, content_id: str) -> None:
        super().__init__("This document already exists in the knowledge base.")
        self.content_id = content_id


def _safe_filename(filename: str) -> str:
    name = Path(filename or "document").name
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return (name or "document")[:180]


class ContentIngestionService:
    def __init__(self, session: Session, storage: ObjectStoragePort) -> None:
        self.session = session
        self.storage = storage

    def upload(self, *, content: bytes, filename: str, agent_id: str | None,
               knowledge_base_id: str | None, user_id: str) -> ContentItem:
        if len(content) > MAX_UPLOAD_BYTES:
            raise IngestionFailure("file_too_large", "Files may be at most 20 MB.")
        knowledge = KnowledgeBaseService(self.session)
        base = (knowledge.resolve_legacy_agent_base(agent_id, user_id) if agent_id
                else knowledge.require_active(knowledge_base_id or "", user_id))
        mime_type = detect_document_type(filename, content)
        digest = hashlib.sha256(content).hexdigest()
        duplicate = self.session.query(ContentItem).filter(
            ContentItem.user_id == user_id,
            ContentItem.knowledge_base_id == base.id,
            ContentItem.content_hash == digest,
            ContentItem.status.in_(["queued", "processing", "ready"]),
        ).first()
        if duplicate:
            raise DuplicateContent(duplicate.id)

        now = datetime.now(timezone.utc)
        item_id = str(uuid.uuid4())
        storage_path = f"{user_id}/{base.id}/{item_id}-{_safe_filename(filename)}"
        self.storage.upload(storage_path, content, mime_type)
        item = ContentItem(id=item_id, user_id=user_id, agent_id=agent_id,
                           knowledge_base_id=base.id, filename=_safe_filename(filename),
                           storage_path=storage_path, extracted_text="", status=ContentStatus.QUEUED.value,
                           mime_type=mime_type, size_bytes=len(content), content_hash=digest,
                           extraction_version=1, created_at=now, updated_at=now)
        job = IngestionJob(id=str(uuid.uuid4()), user_id=user_id, content_id=item_id,
                           status="queued", available_at=now, created_at=now, updated_at=now)
        self.session.add_all([item, job])
        emit(self.session, user_id=user_id, resource_type="ingestion", resource_id=item_id,
             event_type="queued", payload={"size_bytes": len(content), "mime_type": mime_type})
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            try:
                self.storage.delete(storage_path)
            except Exception:
                pass
            raise
        self.session.refresh(item)
        return item

    def get_owned(self, content_id: str, user_id: str) -> ContentItem:
        item = self.session.query(ContentItem).filter(
            ContentItem.id == content_id, ContentItem.user_id == user_id).first()
        if not item:
            raise ContentNotFound("Content item not found")
        return item

    def retry(self, content_id: str, user_id: str) -> ContentItem:
        item = self.get_owned(content_id, user_id)
        KnowledgeBaseService(self.session).require_active(item.knowledge_base_id, user_id)
        if item.status != ContentStatus.FAILED.value:
            raise IngestionFailure("invalid_state", "Only failed documents can be retried.")
        now = datetime.now(timezone.utc)
        job = self.session.query(IngestionJob).filter(
            IngestionJob.content_id == item.id, IngestionJob.user_id == user_id).first()
        if not job:
            job = IngestionJob(user_id=user_id, content_id=item.id)
            self.session.add(job)
        job.status = "queued"
        job.attempt_count = 0
        job.available_at = now
        job.lease_owner = job.lease_until = None
        job.last_error_code = job.last_error_message = None
        job.completed_at = None
        job.updated_at = now
        item.status = ContentStatus.QUEUED.value
        item.error_code = item.error_message = None
        item.index_status = "pending"
        item.index_error_code = item.index_error_message = None
        item.updated_at = now
        emit(self.session, user_id=user_id, resource_type="ingestion", resource_id=item.id,
             event_type="queued", payload={"retry": True})
        self.session.commit()
        self.session.refresh(item)
        return item

    def delete(self, content_id: str, user_id: str) -> None:
        item = self.get_owned(content_id, user_id)
        KnowledgeBaseService(self.session).require_active(item.knowledge_base_id, user_id)
        path = item.storage_path
        self.session.delete(item)
        self.session.commit()
        try:
            self.storage.delete(path)
        except Exception:
            # Metadata deletion is authoritative; orphan reconciliation is a later milestone.
            pass
