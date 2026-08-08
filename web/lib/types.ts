export interface Skill {
  id: string;
  name: string;
  system_prompt: string;
  user_prompt_template: string;
  version: number;
  is_published: boolean;
}

export interface SchemaEntry {
  id: string;
  name: string;
  kind: "input" | "output";
  json_schema: Record<string, unknown>;
  version: string;
}

export interface SecretMeta {
  id: string;
  name: string;
}

export interface PlatformTool {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
}

export type CatalogToolSource = "platform" | "mcp" | "connector";

export interface CatalogTool {
  id: string;
  source: CatalogToolSource;
  name: string;
  description: string;
  status: "Available" | "Needs agent content" | "Connected" | "Configured";
  sourceLabel: string;
  inputSchema?: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
  configuration?: Record<string, unknown>;
  setupHref?: string;
}

export interface McpServer {
  id: string;
  name: string;
  url: string;
  secret_ref: string | null;
}

export interface McpTool {
  id: string;
  tool_name: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
}

export interface Connector {
  id: string;
  name: string;
  base_url: string;
  auth_secret_ref: string | null;
  request_template: Record<string, unknown>;
}

export interface ContentItem {
  id: string;
  agent_id: string | null;
  knowledge_base_id: string;
  filename: string;
  storage_path: string;
  status: "queued" | "processing" | "ready" | "failed";
  mime_type: string | null;
  size_bytes: number | null;
  page_count: number | null;
  character_count: number | null;
  extraction_version: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  index_status: "pending" | "indexing" | "indexed" | "failed";
  embedding_model: string | null;
  index_version: number | null;
  chunk_count: number;
  indexed_at: string | null;
  index_error_code: string | null;
  index_error_message: string | null;
}

export interface SemanticSearchResult {
  chunk_id: string;
  content_id: string;
  filename: string;
  ordinal: number;
  page_start: number | null;
  page_end: number | null;
  score: number;
  excerpt: string;
}

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  status: "active" | "archived";
  document_count: number;
  created_at: string;
  updated_at: string;
}

export interface Agent {
  id: string;
  name: string;
  agent_type: "task" | "chat" | "workflow";
  domain: string;
  owner: string;
  tags: string[];
  description: string;
  status: "draft" | "active";
  evaluation_gate_enabled: boolean;
}

export interface RuntimeModelConfig {
  provider: "gemini" | "groq" | "openrouter" | "openai" | "anthropic";
  model_id: string;
  temperature: number;
  max_tokens: number;
  timeout_ms: number;
  api_key_secret_ref?: string;
  provider_connection_id?: string;
  usage_tier?: "free" | "standard";
}

export interface ModelDefinition {
  id: string;
  name: string;
  tool_calling: boolean;
  structured_output: boolean;
  context_window: number;
  free_max_output_tokens: number;
}

export interface ModelProvider {
  id: RuntimeModelConfig["provider"];
  name: string;
  free_tier_available: boolean;
  notice: string;
  models: ModelDefinition[];
}

export interface ProviderConnection {
  id: string;
  provider: RuntimeModelConfig["provider"];
  display_name: string;
  validation_status: "valid" | "invalid" | "unverified";
  last_validated_at: string | null;
  created_at: string;
}

export interface RunPreflight {
  usage_tier: "free" | "standard";
  estimated_input_tokens: number;
  likely_subtasks: number;
  selected_tools: number;
  document_count: number;
  limits: Record<string, number>;
  warnings: string[];
  high_complexity: boolean;
}

export interface PromptGuardrailsConfig {
  role: string;
  goal: string;
  guardrail_profile: string;
  context_mode: "minimal" | "standard" | "full";
}

export interface MemoryConfig {
  vector_memory_enabled: boolean;
  graph_memory_enabled: boolean;
  episodic_memory_enabled: boolean;
}

export interface HarnessConfig {
  runtime_engine: "direct" | "langchain";
  runtime_model: RuntimeModelConfig;
  prompt_guardrails: PromptGuardrailsConfig;
  memory: MemoryConfig;
  workflow?: { graph_version: "research_v1"; max_plan_steps: number; max_retrieval_queries: number;
    max_research_cycles: number; max_repair_cycles: number; approval_policy: "mcp_and_connectors" };
}

export interface AgentVersion {
  id: string;
  agent_id: string;
  version_number: number;
  harness_config: HarnessConfig;
  skill_id: string;
  input_schema_id: string | null;
  output_schema_id: string;
  tool_allowlist: string[];
  mcp_tool_allowlist: string[];
  connector_allowlist: string[];
  skill_allowlist: string[];
  is_published: boolean;
  published_at: string | null;
  knowledge_base_ids: string[];
  retrieval_config: {
    mode: "hybrid";
    top_k: number;
    max_per_document: number;
    standard_context_tokens: number;
    free_context_tokens: number;
  };
}

export interface AgentTrigger {
  id: string;
  agent_id: string;
  name: string;
  type: "manual" | "api" | "schedule";
  auth_type: string;
  config: Record<string, unknown>;
  enabled: boolean;
}

export interface Run {
  id: string;
  agent_version_id: string;
  status: "pending" | "queued" | "running" | "waiting_approval" | "completed" | "failed" | "cancelled";
  input: Record<string, unknown>;
  output: (Record<string, unknown> & {
    error?: string;
    failure?: RunFailure;
    partial_output?: Record<string, unknown> | null;
  }) | null;
  started_at: string | null;
  completed_at: string | null;
  citations: RunCitation[];
  grounding_status: "grounded" | "insufficient_evidence" | null;
  retrieval_stats: Record<string, unknown>;
  runtime_engine: "direct" | "langchain" | "langgraph";
  runtime_stats: {
    model_calls?: number;
    tool_calls?: number;
    input_tokens?: number;
    output_tokens?: number;
    provider_latency_ms?: number;
    orchestration_overhead_ms?: number;
    total_duration_ms?: number;
  };
}

export interface RunCitation {
  source_id: string;
  knowledge_base_id: string;
  document_id: string;
  chunk_id: string;
  filename: string;
  page_start: number | null;
  page_end: number | null;
  score: number;
  excerpt: string;
}

export interface ConversationThread {
  id: string;
  agent_id: string;
  agent_version_id: string;
  title: string;
  status: "active" | "archived";
  memory_enabled: boolean;
  summary_present: boolean;
  summary_token_count: number;
  message_token_count: number;
  message_count: number;
  expires_at: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: string;
  thread_id: string;
  role: "user" | "assistant";
  content: { text?: string; output?: Record<string, unknown>; citations?: RunCitation[]; status?: string };
  run_id: string | null;
  token_count: number;
  created_at: string;
}

export interface ConversationTurnResponse {
  run: Run;
  messages: ConversationMessage[];
  memory: { context_tokens: number; summarized: boolean; expires_at: string };
}

export interface WorkflowGraph {
  graph_version: string;
  current_node: string;
  status: string;
  resumable: boolean;
  nodes: Array<{ id: string; events: Array<{ status: string; attempt: number; detail: Record<string, unknown> }> }>;
  edges: Array<{ source: string; target: string }>;
}

export interface WorkflowApproval {
  id: string;
  tool_name: string;
  tool_type: "connector" | "mcp";
  arguments: Record<string, unknown>;
  arguments_hash: string;
  status: "pending" | "approved" | "rejected";
  reason: string;
  created_at: string;
  expires_at: string;
}

export interface RunFailure {
  code: string;
  reason: string;
  retryable: boolean;
  retry_after: string | null;
  recommendations: string[];
  consumed: Record<string, number>;
  limits: Record<string, number>;
}

export interface RunStep {
  step_num: number;
  type: string;
  detail: Record<string, unknown>;
}

export interface EvaluationDataset {
  id: string;
  agent_id: string;
  name: string;
  description: string;
  threshold: number;
  retrieval_recall_threshold: number;
  citation_precision_threshold: number;
  grounding_threshold: number;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
}

export interface EvaluationCase {
  id: string;
  dataset_id: string;
  input: Record<string, unknown>;
  expected_output: Record<string, unknown>;
  compare_fields: string[];
  expected_document_ids: string[];
  expected_chunk_ids: string[];
  retrieval_k: number;
}

export interface EvaluationRun {
  id: string;
  agent_version_id: string;
  dataset_id: string;
  score: number;
  status: "queued" | "running" | "retry_wait" | "passed" | "failed";
  completed_cases: number;
  total_cases: number;
  metrics: Record<string, number>;
  gate_results: Record<string, boolean>;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface EvaluationCaseResult {
  id: string;
  evaluation_case_id: string;
  run_id: string | null;
  status: "passed" | "failed";
  retrieved_sources: RunCitation[];
  expected_evidence: { document_ids: string[]; chunk_ids: string[] };
  metrics: Record<string, number>;
  field_mismatches: Array<{ field: string; expected: unknown; actual: unknown }>;
  latency_ms: number;
  token_usage: Record<string, number>;
  error_code: string | null;
  error_message: string | null;
}
