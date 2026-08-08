import uuid
from datetime import datetime, timedelta, timezone

from langgraph.types import Command
from sqlalchemy import or_

from app.db.models import (AgentVersion, Run, WorkflowApproval, WorkflowExecution,
                           WorkflowJob)
from app.workflows.checkpoints import checkpoint_context, delete_checkpoint_thread
from app.workflows.graph import WorkflowGraph
from app.observability.service import emit, maybe_heartbeat


class WorkflowWorker:
    def __init__(self, session_factory, *, lease_seconds: int = 900) -> None:
        self.session_factory = session_factory
        self.lease_seconds = lease_seconds
        self.worker_id = str(uuid.uuid4())

    def run_once(self) -> bool:
        db = self.session_factory()
        try:
            maybe_heartbeat(self, db, "workflow")
            job = self._claim(db)
            if not job:
                self._cleanup_expired(db)
                return False
            run_id = job.run_id
        finally:
            db.close()
        self._process(run_id)
        return True

    def _claim(self, db):
        now = datetime.now(timezone.utc)
        job = (db.query(WorkflowJob).filter(WorkflowJob.available_at <= now,
            or_(WorkflowJob.status.in_(["queued", "retry_wait"]),
                (WorkflowJob.status == "running") & (WorkflowJob.lease_until < now)))
            .order_by(WorkflowJob.available_at, WorkflowJob.created_at)
            .with_for_update(skip_locked=True).first())
        if not job:
            db.rollback(); return None
        job.status = "running"; job.attempt_count += 1; job.lease_owner = self.worker_id
        job.lease_until = now + timedelta(seconds=self.lease_seconds); job.updated_at = now
        run = db.query(Run).filter(Run.id == job.run_id).first()
        execution = db.query(WorkflowExecution).filter(WorkflowExecution.run_id == job.run_id).one()
        if run: run.status = "running"
        execution.status = "running"; execution.updated_at = now
        emit(db, user_id=execution.user_id, resource_type="workflow", resource_id=job.run_id,
             event_type="started", payload={"attempt": job.attempt_count})
        db.commit(); return job

    def _process(self, run_id: str) -> None:
        db = self.session_factory()
        try:
            job = db.query(WorkflowJob).filter(WorkflowJob.run_id == run_id,
                                               WorkflowJob.lease_owner == self.worker_id).first()
            execution = db.query(WorkflowExecution).filter(WorkflowExecution.run_id == run_id).one()
            run = db.query(Run).filter(Run.id == run_id).one()
            version = db.query(AgentVersion).filter(AgentVersion.id == run.agent_version_id).one()
            if not job or run.status == "cancelled": return
            config = {"configurable": {"thread_id": execution.thread_id}}
            with checkpoint_context() as saver:
                graph = WorkflowGraph(db, saver).compile()
                if execution.pending_interrupt.get("resume"):
                    value = execution.pending_interrupt.pop("resume")
                    result = graph.invoke(Command(resume=value), config=config)
                else:
                    result = graph.invoke({"run_id": run.id, "user_id": run.user_id,
                        "version_id": version.id, "request": run.input, "repair_count": 0}, config=config)
            interrupts = result.get("__interrupt__", []) if isinstance(result, dict) else []
            now = datetime.now(timezone.utc)
            if interrupts:
                payload = getattr(interrupts[0], "value", {})
                execution.pending_interrupt = payload
                execution.status = run.status = "waiting_approval"
                execution.resumable = True
                job.status = "waiting_approval"
                emit(db, user_id=run.user_id, resource_type="workflow", resource_id=run.id,
                     event_type="waiting_approval", payload={"current_node": execution.current_node})
            else:
                execution.status = "completed"; execution.resumable = False
                run.status = "completed"; run.completed_at = run.completed_at or now.isoformat()
                job.status = "succeeded"
                emit(db, user_id=run.user_id, resource_type="workflow", resource_id=run.id,
                     event_type="completed", payload={"current_node": execution.current_node,
                                                      "runtime_stats": run.runtime_stats or {}})
            job.lease_owner = job.lease_until = None; job.updated_at = now; execution.updated_at = now
            db.commit()
        except Exception as exc:
            self._fail(db, run_id, exc)
        finally:
            db.close()

    def _fail(self, db, run_id: str, exc: Exception) -> None:
        job = db.query(WorkflowJob).filter(WorkflowJob.run_id == run_id).first()
        run = db.query(Run).filter(Run.id == run_id).first()
        execution = db.query(WorkflowExecution).filter(WorkflowExecution.run_id == run_id).first()
        if not job or not run or not execution: return
        approved = db.query(WorkflowApproval).filter(WorkflowApproval.run_id == run_id,
                                                      WorkflowApproval.status == "approved").first()
        ambiguous = execution.current_node == "approval" and approved is not None
        code = "external_action_outcome_unknown" if ambiguous else "workflow_execution_failed"
        now = datetime.now(timezone.utc)
        job.last_error_code = code; job.last_error_message = "Workflow execution could not continue safely."
        job.lease_owner = job.lease_until = None
        if not ambiguous and job.attempt_count < job.max_attempts:
            job.status = "retry_wait"; job.available_at = now + timedelta(seconds=(5, 30, 120)[job.attempt_count - 1])
            execution.resumable = True
        else:
            job.status = execution.status = run.status = "failed"; execution.resumable = not ambiguous
            run.output = {"error": code, "failure": {"code": code, "reason": job.last_error_message,
                "retryable": not ambiguous, "recommendations": ["Inspect the graph trace before resuming."],
                "consumed": {}, "limits": {}, "retry_after": None}}
            run.completed_at = now.isoformat()
        emit(db, user_id=run.user_id, resource_type="workflow", resource_id=run.id,
             event_type="retrying" if job.status == "retry_wait" else "failed",
             payload={"code": code, "attempt": job.attempt_count})
        db.commit()

    def _cleanup_expired(self, db) -> None:
        rows = db.query(WorkflowExecution).filter(WorkflowExecution.checkpoint_expires_at < datetime.now(timezone.utc),
                                                  WorkflowExecution.status.in_(["completed", "failed", "cancelled"])).limit(10).all()
        for row in rows:
            try: delete_checkpoint_thread(row.thread_id)
            except Exception: continue
            row.checkpoint_expires_at = datetime.max.replace(tzinfo=timezone.utc)
        if rows: db.commit()
