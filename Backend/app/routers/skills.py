from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.db.crud_helpers import get_owned_or_404
from app.db.models import Skill
from app.db.session import get_db

router = APIRouter(prefix="/skills", tags=["skills"])


class SkillIn(BaseModel):
    name: str
    system_prompt: str
    user_prompt_template: str


class SkillOut(SkillIn):
    id: str
    version: int
    is_published: bool


@router.get("", response_model=list[SkillOut])
def list_skills(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    return db.query(Skill).filter(Skill.user_id == user_id).all()


@router.post("", response_model=SkillOut, status_code=201)
def create_skill(body: SkillIn, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    skill = Skill(user_id=user_id, **body.model_dump())
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


@router.get("/{skill_id}", response_model=SkillOut)
def get_skill(skill_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    return get_owned_or_404(db, Skill, skill_id, user_id)


@router.put("/{skill_id}", response_model=SkillOut)
def update_skill(
    skill_id: str, body: SkillIn, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    skill = get_owned_or_404(db, Skill, skill_id, user_id)
    if skill.is_published:
        # AgentVersion.skill_id is a live FK, not a version snapshot — editing a published
        # skill in place would silently change what an already-published agent runs.
        # Force a copy instead of an in-place edit once a version is in use.
        raise HTTPException(
            status_code=409,
            detail="This skill is published and referenced by agent versions — "
            "create a new skill (or a new draft agent version) instead of editing it in place.",
        )
    for field, value in body.model_dump().items():
        setattr(skill, field, value)
    skill.version += 1
    db.commit()
    db.refresh(skill)
    return skill


@router.post("/{skill_id}/publish", response_model=SkillOut)
def publish_skill(skill_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    skill = get_owned_or_404(db, Skill, skill_id, user_id)
    skill.is_published = True
    db.commit()
    db.refresh(skill)
    return skill


@router.delete("/{skill_id}", status_code=204)
def delete_skill(skill_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    skill = get_owned_or_404(db, Skill, skill_id, user_id)
    db.delete(skill)
    db.commit()
