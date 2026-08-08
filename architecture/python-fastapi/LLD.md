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

## Content ingestion module

`ContentIngestionService` owns upload, duplicate, retry and deletion rules. `ObjectStoragePort`
keeps Supabase replaceable. `DocumentParserFactory` selects PDF or normalized UTF-8 strategies.
SHA-256 plus a partial unique index rejects duplicate active documents inside one knowledge base.

`IngestionWorker` claims due rows with `FOR UPDATE SKIP LOCKED`, records a lease owner/expiry, and
writes lifecycle transitions only while it owns that lease. Expired work can be claimed again, so
processing is at-least-once and completion must remain idempotent. Transient storage failures use
bounded retries; corrupt, encrypted, textless and unsupported documents fail deterministically.
The same worker runs inside FastAPI for free/local deployment or through `python -m app.worker`.

Alembic revision `0003_document_ingestion` backfills legacy extracted documents as `ready`, marks
empty legacy documents `failed`, and creates tenant-matched jobs with owner-only RLS.

## Semantic indexing module

`DeterministicChunker` uses the pinned embedding tokenizer, targets 384 tokens, caps chunks at 480
and retains 48 tokens of overlap. Chunk UUIDs derive from document ID, index version, ordinal and
text hash. `FastEmbedAdapter` returns normalized 384-dimensional vectors in batches of 32.

`IndexingWorker` claims leased PostgreSQL jobs and computes chunks/vectors before its final
transaction. It then replaces the old chunk generation and marks the document indexed atomically.
`SemanticIndexService` performs tenant-filtered cosine search through pgvector and exposes bounded
debug excerpts. Alembic revision `0004_semantic_index` enables pgvector, creates HNSW-indexed chunks,
backfills ready documents and applies tenant-matching foreign keys plus RLS.

## Version knowledge and grounded retrieval

Alembic revision `0005_agent_knowledge_rag` adds tenant-scoped version/base bindings, English
`tsvector`/GIN search, retrieval configuration and run grounding fields. `HybridRetriever` executes
semantic and keyword candidate queries, combines them with Reciprocal Rank Fusion, limits chunks per
document and stops at the configured token budget.

`EvidenceLedger` assigns stable run-local source IDs and is shared by automatic retrieval and tool
calls. Bound runs expose an internal `final_answer` envelope containing the original answer,
citations and grounding status. The executor validates every source ID, stores trusted citation
metadata separately and preserves the original output schema in `run.output`.

## Evaluation execution

`EvaluationService` validates tenant ownership, active datasets, evidence labels and version bindings,
then creates an immutable job snapshot. `EvaluationWorker` claims queued or lease-expired rows, skips
already committed case results, and invokes the existing run executor. Pure metric functions calculate
binary-relevance ranking metrics, citation validity and coverage, grounding compliance, and exact field
mismatches. Aggregate metrics and gate results are persisted; publishing rejects non-terminal, stale,
incomplete, or gate-failing evaluations.

## Direct and LangChain runtime adapters

`RuntimeSessionPort` normalizes initial sends, tool-result turns, token usage and runtime statistics.
`DirectRuntimeSession` times the existing OpenAI-compatible, Anthropic and Gemini sessions.
`LangChainRuntimeSession` maps providers to their LangChain chat integrations, binds application-owned
JSON tool schemas and composes `ChatPromptTemplate | ChatModel` as an LCEL runnable. It converts
LangChain AI/tool messages back into the executor's stable turn contract.

`AgentStudioLangChainRetriever` is a `BaseRetriever` view over the existing hybrid retriever. It returns
LangChain `Document` objects with server-issued evidence metadata, but database filtering, tenant checks,
RRF, context budgets and the evidence ledger remain application-owned. Migration `0007_langchain_runtime`
stores each run's engine, tokens, calls, provider latency and orchestration overhead.
### Workflow module

- `workflows.graph.WorkflowGraph` owns bounded nodes and conditional edges.
- `workflows.worker.WorkflowWorker` owns job leases, retries, resume and checkpoint cleanup.
- `workflows.checkpoints` configures the official PostgreSQL saver with strict encrypted serialization.
- `workflow_execution` is durable public lifecycle state; `workflow_job` is queue ownership;
  `workflow_node_event` is the sanitized graph trace; `workflow_approval` is the human decision record.
- MCP and connector arguments remain inside encrypted graph state. Approval rows contain redacted
  arguments plus a SHA-256 hash binding the decision to the exact action.

### Conversation module

- `conversation_thread` owns version pinning, status, token totals, summary cursor and expiry.
- Immutable `conversation_message` rows retain visible user/assistant turns and their originating run.
- `ConversationMemoryService` allocates history, generates structured summaries and refreshes expiry.
- The executor accepts optional delimited conversation context; ordinary run endpoints pass none.
- Summary calls use the configured model and enter the same free model-call budget.
- Hourly bounded cleanup removes expired memory while preserving separate run audits.

### Observability module

- `activity_event` is an append-only seven-day tenant event log with monotonic replay IDs.
- `emit` sanitizes payloads and participates in the caller's transaction without committing it.
- `/events/stream` uses authenticated fetch SSE, bounded database reads, heartbeats, replay cursors and
  per-tenant connection limits.
- `worker_heartbeat` records ingestion, indexing, evaluation and workflow liveness.
- Health warns after 60 queued seconds and becomes critical after 300 seconds or three missed worker
  heartbeats; these rules never mutate work.
