-- AgentSource — full database schema
-- Target: PostgreSQL 14+, applied via Flyway as a single V1__init.sql (or split further, in this
-- exact dependency order, if you prefer smaller migrations).
-- Generic platform schema — no domain-specific tables. Domain logic lives in JSONB config/prompt
-- content, never in the schema itself.

CREATE EXTENSION IF NOT EXISTS pgcrypto; -- for gen_random_uuid()

-- ============================================================================
-- Secrets
-- ============================================================================

CREATE TABLE secret (
  name          TEXT PRIMARY KEY,
  value         TEXT NOT NULL,          -- encrypted at rest by the app layer, not in plaintext
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- Skills, schemas, prompts (referenced by agent_version)
-- ============================================================================

CREATE TABLE skill (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL UNIQUE,
  body          TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE schema_entry (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL UNIQUE,
  kind          TEXT NOT NULL CHECK (kind IN ('input', 'output')),
  json_schema   JSONB NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE prompt (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL UNIQUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE prompt_version (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  prompt_id     UUID NOT NULL REFERENCES prompt(id),
  version_number INT NOT NULL,
  body          TEXT NOT NULL,
  is_published  BOOLEAN NOT NULL DEFAULT false,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (prompt_id, version_number)
);

-- ============================================================================
-- Tools: platform tools (code) + MCP tools (external/self-hosted servers)
-- ============================================================================

CREATE TABLE platform_tool (
  name          TEXT PRIMARY KEY,       -- must match a registered Tool implementation's bean name
  description   TEXT,
  input_schema  JSONB,
  output_schema JSONB
);

CREATE TABLE mcp_server (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL UNIQUE,
  transport     TEXT NOT NULL CHECK (transport IN ('http', 'stdio')),
  base_url      TEXT,                   -- required if transport = 'http'
  command       TEXT,                   -- required if transport = 'stdio'
  auth_secret_ref TEXT REFERENCES secret(name),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE mcp_tool (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mcp_server_id UUID NOT NULL REFERENCES mcp_server(id) ON DELETE CASCADE,
  tool_name     TEXT NOT NULL,
  description   TEXT,
  input_schema  JSONB,
  UNIQUE (mcp_server_id, tool_name)
);

-- ============================================================================
-- Connectors
-- ============================================================================

CREATE TABLE connector (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL UNIQUE,
  type          TEXT NOT NULL CHECK (type IN ('rest', 'queue', 'llm_task')),
  config        JSONB NOT NULL,         -- e.g. { "url": "...", "method": "POST" } or { "topic": "..." }
  secret_ref    TEXT REFERENCES secret(name),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- Agents
-- ============================================================================

CREATE TABLE agent (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL,
  description   TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE agent_version (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id          UUID NOT NULL REFERENCES agent(id) ON DELETE CASCADE,
  version_number    INT NOT NULL,
  harness_config    JSONB NOT NULL,     -- { toolAllowlist, mcpToolAllowlist, connectorAllowlist, model }
  skill_id          UUID NOT NULL REFERENCES skill(id),
  output_schema_id  UUID NOT NULL REFERENCES schema_entry(id),
  input_schema_id   UUID REFERENCES schema_entry(id),
  is_published      BOOLEAN NOT NULL DEFAULT false,
  published_at      TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (agent_id, version_number)
);

CREATE INDEX idx_agent_version_agent_id ON agent_version(agent_id);

-- ============================================================================
-- Workflows (Tier 1: ordered steps; Tier 2 upgrade adds bpmn_xml + engine wiring)
-- ============================================================================

CREATE TABLE workflow (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE workflow_version (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_id   UUID NOT NULL REFERENCES workflow(id) ON DELETE CASCADE,
  version_number INT NOT NULL,
  steps         JSONB NOT NULL,         -- Tier 1: [ { "type": "agent", "agentVersionId": "..." }, { "type": "connector", "connectorId": "..." } ]
  bpmn_xml      TEXT,                   -- Tier 2 only; NULL when using Tier 1 step execution
  is_published  BOOLEAN NOT NULL DEFAULT false,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (workflow_id, version_number)
);

-- ============================================================================
-- Documents / generic file input (used by runs that take a file as input)
-- ============================================================================

CREATE TABLE document (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  filename      TEXT NOT NULL,
  content_type  TEXT NOT NULL,
  storage_path  TEXT NOT NULL,
  uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- Runs and traces
-- ============================================================================

CREATE TABLE run (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_version_id  UUID NOT NULL REFERENCES agent_version(id),
  workflow_version_id UUID REFERENCES workflow_version(id),   -- NULL for a direct agent-only run
  input             JSONB,
  document_id       UUID REFERENCES document(id),
  status            TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','completed','failed')),
  output            JSONB,
  error             TEXT,
  started_at        TIMESTAMPTZ,
  completed_at      TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_run_agent_version_id ON run(agent_version_id);
CREATE INDEX idx_run_status ON run(status);

CREATE TABLE run_trace (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id        UUID NOT NULL REFERENCES run(id) ON DELETE CASCADE,
  seq_no        INT NOT NULL,
  event_type    TEXT NOT NULL,          -- RUN_STARTED | TOOL_CALL_STARTED | TOOL_CALL_COMPLETED |
                                          -- MCP_TOOL_CALL_STARTED | MCP_TOOL_CALL_COMPLETED |
                                          -- CONNECTOR_CALL_STARTED | CONNECTOR_CALL_COMPLETED |
                                          -- LLM_CALL_STARTED | LLM_CALL_COMPLETED |
                                          -- RUN_COMPLETED | RUN_FAILED
  payload       JSONB NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (run_id, seq_no)
);

CREATE INDEX idx_run_trace_run_id_seq ON run_trace(run_id, seq_no);

-- ============================================================================
-- Evaluation
-- ============================================================================

CREATE TABLE evaluation_dataset (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL UNIQUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE evaluation_case (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  evaluation_dataset_id UUID NOT NULL REFERENCES evaluation_dataset(id) ON DELETE CASCADE,
  input                 JSONB,
  document_id           UUID REFERENCES document(id),
  expected_output       JSONB NOT NULL
);

CREATE TABLE evaluation_run (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_version_id      UUID NOT NULL REFERENCES agent_version(id),
  evaluation_dataset_id UUID NOT NULL REFERENCES evaluation_dataset(id),
  pass_count            INT NOT NULL,
  fail_count            INT NOT NULL,
  score                 NUMERIC(5,4) NOT NULL,
  status                TEXT NOT NULL CHECK (status IN ('passed','failed')),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_evaluation_run_agent_version_id ON evaluation_run(agent_version_id);

-- ============================================================================
-- Publish-gate helper view: latest evaluation status per agent version
-- ============================================================================

CREATE VIEW agent_version_publish_status AS
SELECT
  av.id AS agent_version_id,
  er.status AS latest_evaluation_status,
  er.score AS latest_evaluation_score,
  er.created_at AS latest_evaluation_at
FROM agent_version av
LEFT JOIN LATERAL (
  SELECT status, score, created_at
  FROM evaluation_run
  WHERE evaluation_run.agent_version_id = av.id
  ORDER BY created_at DESC
  LIMIT 1
) er ON true;
