from datetime import datetime, timezone

from croniter import croniter
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Agent, AgentTrigger, AgentVersion, Run
from app.db.session import get_db
from app.runs.executor import execute_run

router = APIRouter(prefix="/internal", tags=["internal"])


def _require_cron_secret(x_internal_cron_secret: str = Header(default="")) -> None:
    if x_internal_cron_secret != settings.internal_cron_secret:
        raise HTTPException(status_code=401, detail="Invalid or missing cron secret")


def _is_due(trigger: AgentTrigger, now: datetime) -> bool:
    cron_expr = trigger.config.get("cron_expr")
    if not cron_expr:
        return False
    last_run_at = trigger.config.get("last_run_at")
    base = datetime.fromisoformat(last_run_at) if last_run_at else now
    if not last_run_at:
        return True
    return now >= croniter(cron_expr, base).get_next(datetime)


@router.post("/run-due-schedules", dependencies=[Depends(_require_cron_secret)])
async def run_due_schedules(db: Session = Depends(get_db)):
    """Hit periodically by a free external cron (GitHub Actions scheduled workflow or Vercel
    Cron Job) — there is no in-process scheduler running on this deployment."""
    now = datetime.now(timezone.utc)
    triggered = []

    schedule_triggers = db.query(AgentTrigger).filter(AgentTrigger.type == "schedule", AgentTrigger.enabled.is_(True)).all()
    for trigger in schedule_triggers:
        if not _is_due(trigger, now):
            continue

        agent = db.query(Agent).filter(Agent.id == trigger.agent_id).first()
        if not agent:
            continue
        version = (
            db.query(AgentVersion)
            .filter(AgentVersion.agent_id == agent.id, AgentVersion.is_published.is_(True))
            .order_by(AgentVersion.version_number.desc())
            .first()
        )
        if not version:
            continue

        run = Run(
            agent_version_id=version.id,
            user_id=agent.user_id,
            trigger_id=trigger.id,
            input=trigger.config.get("input", {}),
            status="pending",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        await execute_run(db, run, version, agent.id, agent.user_id)

        trigger.config = {**trigger.config, "last_run_at": now.isoformat()}
        db.commit()
        triggered.append({"trigger_id": trigger.id, "agent_id": agent.id, "run_id": run.id, "status": run.status})

    return {"checked": len(schedule_triggers), "triggered": triggered}
