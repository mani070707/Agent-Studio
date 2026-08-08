import json
import logging
import time
import uuid
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal
from app.routers import (
    agents,
    connectors,
    content,
    evaluation,
    internal,
    mcp_servers,
    runs,
    schema_entries,
    secrets,
    skills,
    tools,
    triggers,
)
from app.modules.providers.presentation import router as providers_router
from app.modules.knowledge.presentation import router as knowledge_router
from app.modules.content.storage import SupabaseObjectStorage
from app.modules.content.worker import IngestionWorker
from app.modules.semantic.router import embedder as semantic_embedder
from app.modules.semantic.router import router as semantic_router
from app.modules.semantic.worker import IndexingWorker
from app.modules.semantic.metrics import semantic_metrics
from app.evaluation.worker import EvaluationWorker
from app.workflows.checkpoints import setup_checkpoints
from app.workflows.worker import WorkflowWorker
from app.conversations.router import router as conversations_router
from app.conversations.service import purge_expired_conversations
from app.observability.router import router as observability_router, sse_metrics
from app.observability.service import (correlation_id_var, heartbeat, new_correlation_id,
                                       purge_old_events)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("agent_studio")


@asynccontextmanager
async def lifespan(_: FastAPI):
    stop = asyncio.Event()
    tasks = []
    heartbeat_workers = []
    if settings.preload_embedding_model:
        await asyncio.to_thread(semantic_embedder().embed_query, "embedding model readiness")
    if settings.embedded_ingestion_worker:
        worker = IngestionWorker(SessionLocal, SupabaseObjectStorage(), lease_seconds=settings.ingestion_lease_seconds)
        heartbeat_workers.append(("ingestion", worker))

        async def work_loop():
            while not stop.is_set():
                try:
                    worked = await asyncio.to_thread(worker.run_once)
                except Exception:
                    logger.exception("Ingestion worker polling failed; the durable queue will retry")
                    worked = False
                if not worked:
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=settings.ingestion_poll_seconds)
                    except TimeoutError:
                        pass

        tasks.append(asyncio.create_task(work_loop()))
    if settings.embedded_indexing_worker:
        async def index_loop(index_worker: IndexingWorker):
            while not stop.is_set():
                try:
                    worked = await asyncio.to_thread(index_worker.run_once)
                except Exception:
                    logger.exception("Indexing worker polling failed; the durable queue will retry")
                    worked = False
                if not worked:
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=settings.indexing_poll_seconds)
                    except TimeoutError:
                        pass

        for _ in range(settings.indexing_worker_concurrency):
            worker_instance = IndexingWorker(
                SessionLocal, semantic_embedder(), index_version=settings.semantic_index_version,
                lease_seconds=settings.indexing_lease_seconds, timeout_seconds=settings.indexing_timeout_seconds,
            )
            heartbeat_workers.append(("indexing", worker_instance))
            tasks.append(asyncio.create_task(index_loop(worker_instance)))
    if settings.embedded_evaluation_worker:
        evaluation_worker = EvaluationWorker(SessionLocal, lease_seconds=settings.evaluation_lease_seconds)
        heartbeat_workers.append(("evaluation", evaluation_worker))

        async def evaluation_loop():
            while not stop.is_set():
                try:
                    worked = await asyncio.to_thread(evaluation_worker.run_once)
                except Exception:
                    logger.exception("Evaluation worker polling failed; the durable queue will retry")
                    worked = False
                if not worked:
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=settings.evaluation_poll_seconds)
                    except TimeoutError:
                        pass

        tasks.append(asyncio.create_task(evaluation_loop()))
    if settings.embedded_workflow_worker and settings.checkpoint_encryption_key:
        await asyncio.to_thread(setup_checkpoints)
        workflow_worker = WorkflowWorker(SessionLocal, lease_seconds=settings.workflow_lease_seconds)
        heartbeat_workers.append(("workflow", workflow_worker))

        async def workflow_loop():
            while not stop.is_set():
                try:
                    worked = await asyncio.to_thread(workflow_worker.run_once)
                except Exception:
                    logger.exception("Workflow worker polling failed; the durable queue will retry")
                    worked = False
                if not worked:
                    try: await asyncio.wait_for(stop.wait(), timeout=settings.workflow_poll_seconds)
                    except TimeoutError: pass

        tasks.append(asyncio.create_task(workflow_loop()))
    elif settings.embedded_workflow_worker:
        logger.warning("Workflow worker disabled: CHECKPOINT_ENCRYPTION_KEY is not configured")
    async def conversation_cleanup_loop():
        while not stop.is_set():
            try:
                await asyncio.to_thread(_purge_conversations)
            except Exception:
                logger.exception("Conversation retention cleanup failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.conversation_cleanup_seconds)
            except TimeoutError:
                pass

    def _purge_conversations():
        db = SessionLocal()
        try:
            purge_expired_conversations(db)
            purge_old_events(db, settings.event_retention_days)
        finally: db.close()

    tasks.append(asyncio.create_task(conversation_cleanup_loop()))
    yield
    stop.set()
    if tasks:
        await asyncio.gather(*tasks)
    db = SessionLocal()
    try:
        for worker_type, worker in heartbeat_workers:
            heartbeat(db, worker_type, worker.worker_id, status="offline")
    finally: db.close()


def create_app() -> FastAPI:
    return FastAPI(title="Agent Studio API", version="1.0.0", lifespan=lifespan)


app = create_app()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    correlation_id = request.headers.get("x-correlation-id") or new_correlation_id()
    token = correlation_id_var.set(correlation_id)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(json.dumps({"event": "request_failed", "method": request.method,
                                     "path": request.url.path, "correlation_id": correlation_id}))
        raise
    finally:
        correlation_id_var.reset(token)
    duration_ms = (time.monotonic() - start) * 1000
    response.headers["x-correlation-id"] = correlation_id
    logger.info(json.dumps({"event": "request_completed", "method": request.method,
                            "path": request.url.path, "status": response.status_code,
                            "duration_ms": round(duration_ms, 1), "correlation_id": correlation_id}))
    return response


app.include_router(skills.router)
app.include_router(schema_entries.router)
app.include_router(secrets.router)
app.include_router(tools.router)
app.include_router(mcp_servers.router)
app.include_router(connectors.router)
app.include_router(content.router)
app.include_router(agents.router)
app.include_router(triggers.router)
app.include_router(runs.router)
app.include_router(evaluation.router)
app.include_router(internal.router)
app.include_router(providers_router)
app.include_router(knowledge_router)
app.include_router(semantic_router)
app.include_router(conversations_router)
app.include_router(observability_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    db = SessionLocal()
    try:
        db.execute(text("select 1"))
        return {"status": "ready"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    finally:
        db.close()


@app.get("/metrics", include_in_schema=False)
def metrics(authorization: str = Header(default="")) -> Response:
    if settings.metrics_token and authorization != f"Bearer {settings.metrics_token}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    lines = ["agent_studio_up 1"]
    db = SessionLocal()
    try:
        queue = db.execute(text("""
            select count(*) filter (where status in ('queued', 'retry_wait')) as depth,
                   coalesce(extract(epoch from (
                     now() - min(created_at) filter (where status in ('queued', 'retry_wait'))
                   )), 0) as oldest_seconds,
                   coalesce(sum(greatest(attempt_count - 1, 0)), 0) as retries
            from ingestion_job
        """)).mappings().one()
        lines.extend([
            f"agent_studio_ingestion_queue_depth {queue['depth']}",
            f"agent_studio_ingestion_oldest_job_seconds {float(queue['oldest_seconds']):.3f}",
            f"agent_studio_ingestion_retry_total {queue['retries']}",
        ])
        failures = db.execute(text("""
            select coalesce(last_error_code, 'unknown') as code, count(*) as total
            from ingestion_job where status = 'failed'
            group by coalesce(last_error_code, 'unknown')
        """)).mappings()
        for failure in failures:
            code = str(failure["code"]).replace('"', "")
            lines.append(f'agent_studio_ingestion_failure_total{{code="{code}"}} {failure["total"]}')
        index_queue = db.execute(text("""
            select count(*) filter (where status in ('queued', 'retry_wait')) as depth,
                   coalesce(extract(epoch from (
                     now() - min(created_at) filter (where status in ('queued', 'retry_wait'))
                   )), 0) as oldest_seconds,
                   coalesce(sum(greatest(attempt_count - 1, 0)), 0) as retries
            from indexing_job
        """)).mappings().one()
        lines.extend([
            f"agent_studio_indexing_queue_depth {index_queue['depth']}",
            f"agent_studio_indexing_oldest_job_seconds {float(index_queue['oldest_seconds']):.3f}",
            f"agent_studio_indexing_retry_total {index_queue['retries']}",
            *semantic_metrics.prometheus_lines(),
        ])
        evaluation_queue = db.execute(text("""
            select count(*) filter(where status in ('queued','retry_wait')) depth,
                   count(*) filter(where status='running') running,
                   coalesce(extract(epoch from(now()-min(created_at) filter(where status in ('queued','retry_wait')))),0) oldest
            from evaluation_run
        """)).mappings().one()
        lines.extend([
            f"agent_studio_evaluation_queue_depth {evaluation_queue['depth']}",
            f"agent_studio_evaluation_running {evaluation_queue['running']}",
            f"agent_studio_evaluation_oldest_job_seconds {float(evaluation_queue['oldest']):.3f}",
        ])
        workflow_queue = db.execute(text("""
            select count(*) filter(where status in ('queued','retry_wait')) depth,
                   count(*) filter(where status='waiting_approval') waiting,
                   coalesce(extract(epoch from(now()-min(created_at) filter(where status in ('queued','retry_wait')))),0) oldest
            from workflow_job
        """)).mappings().one()
        lines.extend([f"agent_studio_workflow_queue_depth {workflow_queue['depth']}",
                      f"agent_studio_workflow_waiting_approval {workflow_queue['waiting']}",
                      f"agent_studio_workflow_oldest_job_seconds {float(workflow_queue['oldest']):.3f}"])
        conversations = db.execute(text("""
            select count(*) filter(where status='active') active,
                   coalesce(sum(message_token_count + summary_token_count),0) tokens,
                   count(*) filter(where summary_token_count > 0) summarized,
                   count(*) filter(where expires_at < now()) expired
            from conversation_thread
        """)).mappings().one()
        lines.extend([f"agent_studio_conversation_active {conversations['active']}",
                      f"agent_studio_conversation_memory_tokens {conversations['tokens']}",
                      f"agent_studio_conversation_summarized {conversations['summarized']}",
                      f"agent_studio_conversation_expired_pending_cleanup {conversations['expired']}"])
        active_sse, reconnects = sse_metrics()
        event_count = db.execute(text("select count(*) from activity_event")).scalar() or 0
        event_failures = db.execute(text("""select event_type,count(*) total from activity_event
            where event_type in ('failed','retrying') group by event_type""")).mappings()
        heartbeat_age = db.execute(text("select coalesce(max(extract(epoch from(now()-last_seen_at))),0) from worker_heartbeat")).scalar() or 0
        lines.extend([f"agent_studio_sse_active_connections {active_sse}",
                      f"agent_studio_sse_reconnect_total {reconnects}",
                      f"agent_studio_activity_event_total {event_count}",
                      f"agent_studio_worker_max_heartbeat_age_seconds {float(heartbeat_age):.3f}"])
        for failure in event_failures:
            lines.append(f'agent_studio_activity_failure_total{{type="{failure["event_type"]}"}} {failure["total"]}')
    finally:
        db.close()
    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
