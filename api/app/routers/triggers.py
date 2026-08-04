from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.db.crud_helpers import get_owned_or_404
from app.db.models import Agent, AgentTrigger
from app.db.session import get_db

router = APIRouter(prefix="/agents/{agent_id}/triggers", tags=["triggers"])


class TriggerIn(BaseModel):
    name: str
    type: Literal["manual", "api", "schedule"]
    auth_type: str = ""
    config: dict = {}
    enabled: bool = True


class TriggerOut(TriggerIn):
    id: str
    agent_id: str


@router.get("", response_model=list[TriggerOut])
def list_triggers(agent_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    get_owned_or_404(db, Agent, agent_id, user_id)
    return db.query(AgentTrigger).filter(AgentTrigger.agent_id == agent_id).all()


@router.post("", response_model=TriggerOut, status_code=201)
def create_trigger(
    agent_id: str, body: TriggerIn, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    get_owned_or_404(db, Agent, agent_id, user_id)
    if body.type == "schedule" and "cron_expr" not in body.config:
        raise HTTPException(status_code=400, detail="schedule triggers require config.cron_expr")
    trigger = AgentTrigger(agent_id=agent_id, **body.model_dump())
    db.add(trigger)
    db.commit()
    db.refresh(trigger)
    return trigger


@router.put("/{trigger_id}", response_model=TriggerOut)
def update_trigger(
    agent_id: str,
    trigger_id: str,
    body: TriggerIn,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    get_owned_or_404(db, Agent, agent_id, user_id)
    trigger = db.query(AgentTrigger).filter(AgentTrigger.id == trigger_id, AgentTrigger.agent_id == agent_id).first()
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    for field, value in body.model_dump().items():
        setattr(trigger, field, value)
    db.commit()
    db.refresh(trigger)
    return trigger


@router.delete("/{trigger_id}", status_code=204)
def delete_trigger(
    agent_id: str, trigger_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    get_owned_or_404(db, Agent, agent_id, user_id)
    trigger = db.query(AgentTrigger).filter(AgentTrigger.id == trigger_id, AgentTrigger.agent_id == agent_id).first()
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    db.delete(trigger)
    db.commit()
