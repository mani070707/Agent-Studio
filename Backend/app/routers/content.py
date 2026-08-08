import tempfile
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.db.crud_helpers import get_owned_or_404
from app.db.models import Agent, ContentItem
from app.db.session import get_db
from app.modules.content.domain import IngestionFailure
from app.modules.content.service import ContentIngestionService, ContentNotFound, DuplicateContent, MAX_UPLOAD_BYTES
from app.modules.content.storage import SupabaseObjectStorage
from app.modules.knowledge.application import KnowledgeBaseConflict, KnowledgeBaseNotFound

router = APIRouter(prefix="/content", tags=["content"])


class ContentItemOut(BaseModel):
    id: str
    agent_id: str | None
    knowledge_base_id: str
    filename: str
    storage_path: str
    status: str
    mime_type: str | None
    size_bytes: int | None
    page_count: int | None
    character_count: int | None
    extraction_version: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    index_status: str
    embedding_model: str | None
    index_version: int | None
    chunk_count: int
    indexed_at: datetime | None
    index_error_code: str | None
    index_error_message: str | None


def _service(db: Session) -> ContentIngestionService:
    return ContentIngestionService(db, SupabaseObjectStorage())


def _raise_domain(exc: Exception) -> None:
    if isinstance(exc, (ContentNotFound, KnowledgeBaseNotFound)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, DuplicateContent):
        raise HTTPException(status_code=409, detail={"code": "duplicate_content", "message": str(exc),
                                                     "existing_content_id": exc.content_id}) from exc
    if isinstance(exc, KnowledgeBaseConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, IngestionFailure):
        status = 413 if exc.code == "file_too_large" else 415 if exc.code == "unsupported_type" else 422
        raise HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message}) from exc
    raise exc


@router.get("", response_model=list[ContentItemOut])
def list_content(agent_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    get_owned_or_404(db, Agent, agent_id, user_id)
    return (db.query(ContentItem).filter(ContentItem.agent_id == agent_id, ContentItem.user_id == user_id)
            .order_by(ContentItem.created_at.desc(), ContentItem.id).all())


@router.post("", response_model=ContentItemOut, status_code=201)
async def upload_content(response: Response, file: UploadFile, agent_id: str | None = None,
                         knowledge_base_id: str | None = None, db: Session = Depends(get_db),
                         user_id: str = Depends(get_current_user_id)):
    if bool(agent_id) == bool(knowledge_base_id):
        raise HTTPException(status_code=422, detail="Provide exactly one of agent_id or knowledge_base_id")
    with tempfile.SpooledTemporaryFile(max_size=2 * 1024 * 1024) as temporary:
        size = 0
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail={"code": "file_too_large", "message": "Files may be at most 20 MB."})
            temporary.write(chunk)
        temporary.seek(0)
        content = temporary.read()
    try:
        item = _service(db).upload(content=content, filename=file.filename or "document",
                                   agent_id=agent_id, knowledge_base_id=knowledge_base_id, user_id=user_id)
    except Exception as exc:
        _raise_domain(exc)
    response.headers["Location"] = f"/content/{item.id}"
    return item


@router.get("/{content_id}", response_model=ContentItemOut)
def get_content(content_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    try:
        return _service(db).get_owned(content_id, user_id)
    except Exception as exc:
        _raise_domain(exc)


@router.post("/{content_id}/retry", response_model=ContentItemOut)
def retry_content(content_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    try:
        return _service(db).retry(content_id, user_id)
    except Exception as exc:
        _raise_domain(exc)


@router.delete("/{content_id}", status_code=204)
def delete_content(content_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    try:
        _service(db).delete(content_id, user_id)
    except Exception as exc:
        _raise_domain(exc)
