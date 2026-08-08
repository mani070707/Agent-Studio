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
  runtime_model: RuntimeModelConfig;
  prompt_guardrails: PromptGuardrailsConfig;
  memory: MemoryConfig;
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
  status: "pending" | "running" | "completed" | "failed";
  input: Record<string, unknown>;
  output: (Record<string, unknown> & {
    error?: string;
    failure?: RunFailure;
    partial_output?: Record<string, unknown> | null;
  }) | null;
  started_at: string | null;
  completed_at: string | null;
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
  threshold: number;
}

export interface EvaluationCase {
  id: string;
  dataset_id: string;
  input: Record<string, unknown>;
  expected_output: Record<string, unknown>;
  compare_fields: string[];
}

export interface EvaluationRun {
  id: string;
  agent_version_id: string;
  dataset_id: string;
  score: number;
  status: "pending" | "passed" | "failed";
}
