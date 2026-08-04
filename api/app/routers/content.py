import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.content.extraction import extract_text
from app.core.auth import get_current_user_id
from app.db.crud_helpers import get_owned_or_404
from app.db.models import Agent, ContentItem
from app.db.session import get_db
from app.storage.supabase_storage import delete_file, upload_file

router = APIRouter(prefix="/content", tags=["content"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class ContentItemOut(BaseModel):
    id: str
    agent_id: str
    filename: str
    storage_path: str


@router.get("", response_model=list[ContentItemOut])
def list_content(agent_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    get_owned_or_404(db, Agent, agent_id, user_id)
    return db.query(ContentItem).filter(ContentItem.agent_id == agent_id, ContentItem.user_id == user_id).all()


@router.post("", response_model=ContentItemOut, status_code=201)
async def upload_content(
    agent_id: str,
    file: UploadFile,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    get_owned_or_404(db, Agent, agent_id, user_id)

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")

    storage_path = f"{user_id}/{agent_id}/{uuid.uuid4()}-{file.filename}"
    upload_file(storage_path, content, content_type=file.content_type or "application/octet-stream")
    extracted_text = extract_text(file.filename, content)

    item = ContentItem(
        user_id=user_id,
        agent_id=agent_id,
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
    delete_file(item.storage_path)
    db.delete(item)
    db.commit()
