from datetime import datetime, timezone
import time

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import ContentItem, DocumentChunk, IndexingJob, KnowledgeBase
from app.modules.knowledge.application import KnowledgeBaseConflict, KnowledgeBaseNotFound, KnowledgeBaseService
from app.modules.semantic.domain import IndexFailure, SearchHit
from app.modules.semantic.ports import EmbeddingPort
from app.modules.semantic.metrics import semantic_metrics


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.9g}" for value in vector) + "]"


class SemanticIndexService:
    def __init__(self, session: Session, embedder: EmbeddingPort) -> None:
        self.session = session
        self.embedder = embedder

    def list_chunks(self, content_id: str, user_id: str, offset: int, limit: int) -> list[DocumentChunk]:
        item = self._content(content_id, user_id)
        return (self.session.query(DocumentChunk)
                .filter(DocumentChunk.content_id == item.id, DocumentChunk.user_id == user_id)
                .order_by(DocumentChunk.ordinal).offset(offset).limit(limit).all())

    def reindex(self, content_id: str, user_id: str) -> ContentItem:
        item = self._content(content_id, user_id)
        KnowledgeBaseService(self.session).require_active(item.knowledge_base_id, user_id)
        if item.status != "ready":
            raise IndexFailure("extraction_not_ready", "Text extraction must succeed before indexing.")
        if item.index_status not in {"failed", "indexed"}:
            raise IndexFailure("invalid_index_state", "This document is already queued or indexing.")
        now = datetime.now(timezone.utc)
        job = self.session.query(IndexingJob).filter(
            IndexingJob.content_id == item.id, IndexingJob.user_id == user_id).first()
        if not job:
            job = IndexingJob(user_id=user_id, content_id=item.id)
            self.session.add(job)
        job.status = "queued"
        job.attempt_count = 0
        job.available_at = now
        job.lease_owner = job.lease_until = None
        job.last_error_code = job.last_error_message = None
        job.completed_at = None
        job.updated_at = now
        item.index_status = "pending"
        item.index_error_code = item.index_error_message = None
        item.updated_at = now
        self.session.commit()
        self.session.refresh(item)
        return item

    def search(self, knowledge_base_id: str, user_id: str, query: str,
               limit: int, min_score: float | None) -> list[SearchHit]:
        started = time.monotonic()
        normalized = query.strip()
        if not normalized:
            raise IndexFailure("blank_query", "Search query cannot be blank.")
        if len(normalized) > 4_000:
            raise IndexFailure("query_too_large", "Search query may contain at most 4,000 characters.")
        base = self.session.query(KnowledgeBase).filter(
            KnowledgeBase.id == knowledge_base_id, KnowledgeBase.user_id == user_id).first()
        if not base:
            raise KnowledgeBaseNotFound("Knowledge base not found")
        embedding = vector_literal(self.embedder.embed_query(normalized))
        rows = self.session.execute(text("""
            select dc.id chunk_id, dc.content_id, ci.filename, dc.ordinal,
                   dc.page_start, dc.page_end,
                   1 - (dc.embedding <=> cast(:embedding as extensions.vector)) as score,
                   left(dc.text, 800) as excerpt
            from document_chunk dc
            join content_item ci on ci.id = dc.content_id and ci.user_id = dc.user_id
            where dc.user_id = cast(:user_id as uuid)
              and dc.knowledge_base_id = :knowledge_base_id
              and ci.index_status = 'indexed'
              and (:min_score is null or 1 - (dc.embedding <=> cast(:embedding as extensions.vector)) >= :min_score)
            order by dc.embedding <=> cast(:embedding as extensions.vector), dc.id
            limit :limit
        """), {"embedding": embedding, "user_id": user_id, "knowledge_base_id": knowledge_base_id,
                 "min_score": min_score, "limit": limit}).mappings()
        hits = [SearchHit(row["chunk_id"], row["content_id"], row["filename"], row["ordinal"],
                          row["page_start"], row["page_end"], float(row["score"]), row["excerpt"])
                for row in rows]
        semantic_metrics.record_search(time.monotonic() - started)
        return hits

    def _content(self, content_id: str, user_id: str) -> ContentItem:
        item = self.session.query(ContentItem).filter(
            ContentItem.id == content_id, ContentItem.user_id == user_id).first()
        if not item:
            raise KnowledgeBaseNotFound("Content item not found")
        return item
