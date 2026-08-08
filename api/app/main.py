import json
import logging
import time
import uuid

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("agent_studio")


def create_app() -> FastAPI:
    return FastAPI(title="Agent Studio API", version="1.0.0")


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
    correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(json.dumps({"event": "request_failed", "method": request.method,
                                     "path": request.url.path, "correlation_id": correlation_id}))
        raise
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
    return Response("agent_studio_up 1\n", media_type="text/plain; version=0.0.4")
