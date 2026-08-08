# Agent Studio Python/FastAPI — Low-Level Design

## Module structure

Each business module contains `domain`, `application`, `infrastructure` and `presentation` layers.
Domain types have no FastAPI, SQLAlchemy or provider-SDK imports. Application services implement
use cases. Infrastructure classes implement repositories and external adapters. Presentation owns
Pydantic DTOs and thin HTTP handlers.

## Applied patterns

- Repository: tenant-scoped persistence operations.
- Unit of Work: one transaction per application command.
- Ports and adapters: model, storage, MCP and connector isolation.
- Strategy/Factory: provider and tool selection.
- Policy object: execution budgets, publishing and authorization rules.
- Dependency injection: FastAPI dependency providers construct use cases.

FastAPI may execute current synchronous persistence handlers in its thread pool while modules are
converted incrementally to SQLAlchemy async sessions. External HTTP and model operations use async
clients on runtime paths. Blocking PDF parsing is delegated to a worker thread and later to durable
jobs.

## Data and API compatibility

Existing IDs, snake_case fields, JSONB layouts and Fernet ciphertext remain unchanged. Alembic's
baseline represents the existing schema; live databases are stamped and fresh databases execute
the baseline. Public routes remain stable throughout refactoring.

## Knowledge module

`modules/knowledge` separates domain naming/status rules, the `KnowledgeBaseService`, a
tenant-scoped SQLAlchemy repository and FastAPI presentation DTOs. The database enforces matching
tenant IDs between knowledge bases and content through a composite foreign key, while RLS provides
defense in depth. Alembic revision `0002_knowledge_bases` backfills legacy documents and retains
nullable `agent_id` only for compatibility.
