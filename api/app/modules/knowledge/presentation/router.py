from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.db.session import get_db
from app.modules.knowledge.application import KnowledgeBaseConflict, KnowledgeBaseNotFound, KnowledgeBaseService
from app.modules.knowledge.domain import KnowledgeBaseStatus

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


class KnowledgeBaseWrite(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""


class KnowledgeBaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    status: KnowledgeBaseStatus
    document_count: int
    created_at: datetime
    updated_at: datetime


class ContentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    agent_id: str | None
    knowledge_base_id: str
    filename: str
    storage_path: str


def service(db: Session = Depends(get_db)) -> KnowledgeBaseService:
    return KnowledgeBaseService(db)


def translate(exc: Exception) -> HTTPException:
    if isinstance(exc, KnowledgeBaseNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, KnowledgeBaseConflict):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="Knowledge-base operation failed")


@router.get("", response_model=list[KnowledgeBaseResponse])
def list_knowledge_bases(status: KnowledgeBaseStatus = KnowledgeBaseStatus.ACTIVE,
                         user_id: str = Depends(get_current_user_id), use_case=Depends(service)):
    return use_case.list(user_id, status)


@router.post("", response_model=KnowledgeBaseResponse, status_code=201)
def create_knowledge_base(body: KnowledgeBaseWrite, user_id: str = Depends(get_current_user_id),
                          use_case=Depends(service)):
    try:
        return use_case.create(body.name, body.description, user_id)
    except Exception as exc:
        raise translate(exc) from exc


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseResponse)
def get_knowledge_base(knowledge_base_id: str, user_id: str = Depends(get_current_user_id),
                       use_case=Depends(service)):
    try:
        return use_case.get(knowledge_base_id, user_id)
    except Exception as exc:
        raise translate(exc) from exc


@router.put("/{knowledge_base_id}", response_model=KnowledgeBaseResponse)
def update_knowledge_base(knowledge_base_id: str, body: KnowledgeBaseWrite,
                          user_id: str = Depends(get_current_user_id), use_case=Depends(service)):
    try:
        return use_case.update(knowledge_base_id, body.name, body.description, user_id)
    except Exception as exc:
        raise translate(exc) from exc


@router.delete("/{knowledge_base_id}", status_code=204)
def archive_knowledge_base(knowledge_base_id: str, user_id: str = Depends(get_current_user_id),
                           use_case=Depends(service)):
    try:
        use_case.archive(knowledge_base_id, user_id)
        return Response(status_code=204)
    except Exception as exc:
        raise translate(exc) from exc


@router.get("/{knowledge_base_id}/content", response_model=list[ContentResponse])
def list_knowledge_base_content(knowledge_base_id: str, user_id: str = Depends(get_current_user_id),
                                use_case=Depends(service)):
    try:
        return use_case.list_content(knowledge_base_id, user_id)
    except Exception as exc:
        raise translate(exc) from exc
