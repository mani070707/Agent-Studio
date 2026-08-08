import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.content.extraction import extract_text
from app.core.auth import get_current_user_id
from app.db.crud_helpers import get_owned_or_404
from app.db.models import Agent, ContentItem
from app.db.session import get_db
from app.modules.knowledge.application import KnowledgeBaseConflict, KnowledgeBaseNotFound, KnowledgeBaseService
from app.storage.supabase_storage import delete_file, upload_file

router = APIRouter(prefix="/content", tags=["content"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class ContentItemOut(BaseModel):
    id: str
    agent_id: str | None
    knowledge_base_id: str
    filename: str
    storage_path: str


@router.get("", response_model=list[ContentItemOut])
def list_content(agent_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    get_owned_or_404(db, Agent, agent_id, user_id)
    return db.query(ContentItem).filter(ContentItem.agent_id == agent_id, ContentItem.user_id == user_id).all()


@router.post("", response_model=ContentItemOut, status_code=201)
async def upload_content(
    file: UploadFile,
    agent_id: str | None = None,
    knowledge_base_id: str | None = None,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    if bool(agent_id) == bool(knowledge_base_id):
        raise HTTPException(status_code=422, detail="Provide exactly one of agent_id or knowledge_base_id")

    knowledge = KnowledgeBaseService(db)
    try:
        if agent_id:
            knowledge_base = knowledge.resolve_legacy_agent_base(agent_id, user_id)
        else:
            knowledge_base = knowledge.require_active(knowledge_base_id or "", user_id)
    except KnowledgeBaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KnowledgeBaseConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")

    storage_path = f"{user_id}/{knowledge_base.id}/{uuid.uuid4()}-{file.filename}"
    upload_file(storage_path, content, content_type=file.content_type or "application/octet-stream")
    extracted_text = extract_text(file.filename, content)

    item = ContentItem(
        user_id=user_id,
        agent_id=agent_id,
        knowledge_base_id=knowledge_base.id,
        filename=file.filename,
        storage_path=storage_path,
        extracted_text=extracted_text,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{content_id}", status_code=204)
def delete_content(content_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    item = get_owned_or_404(db, ContentItem, content_id, user_id)
    try:
        KnowledgeBaseService(db).require_active(item.knowledge_base_id, user_id)
    except KnowledgeBaseConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    delete_file(item.storage_path)
    db.delete(item)
    db.commit()
