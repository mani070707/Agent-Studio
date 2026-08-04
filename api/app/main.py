import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

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
from app.tools.registry import sync_to_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("agent_studio")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        sync_to_db(db)
        logger.info("Platform tool registry synced to DB at startup")
    finally:
        db.close()
    yield


app = FastAPI(title="Agent Studio API", lifespan=lifespan)

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
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000
    logger.info("%s %s -> %s (%.1fms)", request.method, request.url.path, response.status_code, duration_ms)
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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
