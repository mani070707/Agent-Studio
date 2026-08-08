from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.db.session import get_db
from app.modules.knowledge.application import KnowledgeBaseConflict, KnowledgeBaseNotFound
from app.modules.semantic.domain import IndexFailure
from app.modules.semantic.embedding import FastEmbedAdapter
from app.modules.semantic.service import SemanticIndexService

router = APIRouter(tags=["semantic-index"])
_embedder: FastEmbedAdapter | None = None


def embedder() -> FastEmbedAdapter:
    global _embedder
    if _embedder is None:
        from app.core.config import settings
        _embedder = FastEmbedAdapter(model_name=settings.embedding_model, cache_dir=settings.embedding_cache_dir,
                                     batch_size=settings.embedding_batch_size)
    return _embedder


def service(db: Session = Depends(get_db)) -> SemanticIndexService:
    return SemanticIndexService(db, embedder())


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4_000)
    limit: int = Field(default=5, ge=1, le=20)
    min_score: float | None = Field(default=None, ge=-1, le=1)


class SearchResult(BaseModel):
    chunk_id: str
    content_id: str
    filename: str
    ordinal: int
    page_start: int | None
    page_end: int | None
    score: float
    excerpt: str


class ChunkResult(BaseModel):
    id: str
    ordinal: int
    text: str
    token_count: int
    page_start: int | None
    page_end: int | None
    text_hash: str
    embedding_model: str
    index_version: int
    created_at: datetime


def translate(exc: Exception) -> HTTPException:
    if isinstance(exc, KnowledgeBaseNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (KnowledgeBaseConflict, IndexFailure)):
        return HTTPException(status_code=409 if isinstance(exc, KnowledgeBaseConflict) else 422,
                             detail={"code": getattr(exc, "code", "conflict"), "message": str(exc)})
    return HTTPException(status_code=500, detail="Semantic-index operation failed")


@router.post("/knowledge-bases/{knowledge_base_id}/search", response_model=list[SearchResult])
def search(knowledge_base_id: str, body: SearchRequest, user_id: str = Depends(get_current_user_id),
           use_case: SemanticIndexService = Depends(service)):
    try:
        return use_case.search(knowledge_base_id, user_id, body.query, body.limit, body.min_score)
    except Exception as exc:
        raise translate(exc) from exc


@router.get("/content/{content_id}/chunks", response_model=list[ChunkResult])
def chunks(content_id: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
           user_id: str = Depends(get_current_user_id), use_case: SemanticIndexService = Depends(service)):
    try:
        return use_case.list_chunks(content_id, user_id, offset, limit)
    except Exception as exc:
        raise translate(exc) from exc


@router.post("/content/{content_id}/reindex")
def reindex(content_id: str, user_id: str = Depends(get_current_user_id),
            use_case: SemanticIndexService = Depends(service)):
    try:
        item = use_case.reindex(content_id, user_id)
        return {"id": item.id, "index_status": item.index_status}
    except Exception as exc:
        raise translate(exc) from exc
