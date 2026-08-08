"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { PageHero } from "@/components/ui";
import type {
  Agent,
  AgentTrigger,
  AgentVersion,
  Connector,
  McpServer,
  McpTool,
  PlatformTool,
  ModelDefinition,
  ModelProvider,
  ProviderConnection,
  RuntimeModelConfig,
  KnowledgeBase,
  SchemaEntry,
  Skill,
} from "@/lib/types";

const STEPS = ["Harness", "Trigger", "Evaluation", "Review"];

function toggleInList(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

export default function EditAgentPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const router = useRouter();

  const [step, setStep] = useState(0);
  const [agent, setAgent] = useState<Agent | null>(null);
  const [draft, setDraft] = useState<AgentVersion | null>(null);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [schemas, setSchemas] = useState<SchemaEntry[]>([]);
  const [platformTools, setPlatformTools] = useState<PlatformTool[]>([]);
  const [mcpTools, setMcpTools] = useState<(McpTool & { serverName: string })[]>([]);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [triggers, setTriggers] = useState<AgentTrigger[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const [provider, setProvider] = useState<RuntimeModelConfig["provider"]>("gemini");
  const [runtimeEngine, setRuntimeEngine] = useState<"direct" | "langchain">("direct");
  const [modelId, setModelId] = useState("gemini-2.5-flash");
  const [apiKeySecretRef, setApiKeySecretRef] = useState("");
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [connections, setConnections] = useState<ProviderConnection[]>([]);
  const [models, setModels] = useState<ModelDefinition[]>([]);
  const [providerConnectionId, setProviderConnectionId] = useState("");
  const [usageTier, setUsageTier] = useState<"free" | "standard">("standard");
  const [connectionMode, setConnectionMode] = useState<"saved" | "new">("saved");
  const [connectionName, setConnectionName] = useState("");
  const [newApiKey, setNewApiKey] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [temperature, setTemperature] = useState(0);
  const [maxTokens, setMaxTokens] = useState(4096);
  const [role, setRole] = useState("");
  const [goal, setGoal] = useState("");
  const [guardrailProfile, setGuardrailProfile] = useState("standard");
  const [contextMode, setContextMode] = useState<"minimal" | "standard" | "full">("minimal");
  const [skillId, setSkillId] = useState("");
  const [inputSchemaId, setInputSchemaId] = useState("");
  const [outputSchemaId, setOutputSchemaId] = useState("");
  const [toolAllowlist, setToolAllowlist] = useState<string[]>([]);
  const [mcpToolAllowlist, setMcpToolAllowlist] = useState<string[]>([]);
  const [connectorAllowlist, setConnectorAllowlist] = useState<string[]>([]);
  const [skillAllowlist, setSkillAllowlist] = useState<string[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [knowledgeBaseIds, setKnowledgeBaseIds] = useState<string[]>([]);
  const [conversationMemory, setConversationMemory] = useState(false);

  const [newTrigger, setNewTrigger] = useState<{
    name: string;
    type: AgentTrigger["type"];
    cron_expr: string;
  }>({ name: "", type: "manual", cron_expr: "" });

  useEffect(() => {
    async function load() {
      const [agentData, versions, skillsData, schemasData, toolsData, mcpServers, connectorsData, triggersData,
        providersData, connectionsData, knowledgeBaseData] =
        await Promise.all([
          api.get<Agent>(`/agents/${agentId}`),
          api.get<AgentVersion[]>(`/agents/${agentId}/versions`),
          api.get<Skill[]>("/skills"),
          api.get<SchemaEntry[]>("/schemas"),
          api.get<PlatformTool[]>("/tools/platform"),
          api.get<McpServer[]>("/mcp-servers"),
          api.get<Connector[]>("/connectors"),
          api.get<AgentTrigger[]>(`/agents/${agentId}/triggers`),
          api.get<ModelProvider[]>("/model-providers"),
          api.get<ProviderConnection[]>("/provider-connections"),
          api.get<KnowledgeBase[]>("/knowledge-bases?status=active"),
        ]);

      setAgent(agentData);
      setSkills(skillsData);
      setSchemas(schemasData);
      setPlatformTools(toolsData);
      setConnectors(connectorsData);
      setTriggers(triggersData);
      setProviders(providersData);
      setConnections(connectionsData);
      setKnowledgeBases(knowledgeBaseData);

      const flatMcpTools: (McpTool & { serverName: string })[] = [];
      for (const server of mcpServers) {
        const serverTools = await api.get<McpTool[]>(`/mcp-servers/${server.id}/tools`);
        flatMcpTools.push(...serverTools.map((t) => ({ ...t, serverName: server.name })));
      }
      setMcpTools(flatMcpTools);

      const existingDraft = versions.find((v) => !v.is_published) || null;
      setDraft(existingDraft);
      if (existingDraft) {
        setRuntimeEngine(existingDraft.harness_config.runtime_engine || "direct");
        setProvider(existingDraft.harness_config.runtime_model.provider);
        setModelId(existingDraft.harness_config.runtime_model.model_id);
        setApiKeySecretRef(existingDraft.harness_config.runtime_model.api_key_secret_ref || "");
        setProviderConnectionId(existingDraft.harness_config.runtime_model.provider_connection_id || "");
        setUsageTier(existingDraft.harness_config.runtime_model.usage_tier || "standard");
        setTemperature(existingDraft.harness_config.runtime_model.temperature);
        setMaxTokens(existingDraft.harness_config.runtime_model.max_tokens);
        setRole(existingDraft.harness_config.prompt_guardrails.role);
        setGoal(existingDraft.harness_config.prompt_guardrails.goal);
        setGuardrailProfile(existingDraft.harness_config.prompt_guardrails.guardrail_profile);
        setContextMode(existingDraft.harness_config.prompt_guardrails.context_mode);
        setSkillId(existingDraft.skill_id);
        setInputSchemaId(existingDraft.input_schema_id || "");
        setOutputSchemaId(existingDraft.output_schema_id);
        setToolAllowlist(existingDraft.tool_allowlist);
        setMcpToolAllowlist(existingDraft.mcp_tool_allowlist);
        setConnectorAllowlist(existingDraft.connector_allowlist);
        setSkillAllowlist(existingDraft.skill_allowlist);
        setKnowledgeBaseIds(existingDraft.knowledge_base_ids || []);
        setConversationMemory(existingDraft.harness_config.memory?.vector_memory_enabled || false);
      }
      setLoading(false);
    }
    load();
  }, [agentId]);

  useEffect(() => {
    if (!providerConnectionId) { setModels([]); return; }
    api.get<ModelDefinition[]>(`/model-providers/${provider}/models?connection_id=${providerConnectionId}`)
      .then((available) => {
        setModels(available);
        if (available.length && !available.some((model) => model.id === modelId)) setModelId(available[0].id);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)));
  }, [provider, providerConnectionId]);

  async function connectProvider(): Promise<string | null> {
    if (connectionMode === "saved") return providerConnectionId || null;
    if (!connectionName.trim() || !newApiKey.trim()) {
      setError("Connection name and API key are required.");
      return null;
    }
    setConnecting(true);
    try {
      const created = await api.post<ProviderConnection>("/provider-connections", {
        provider, display_name: connectionName.trim(), api_key: newApiKey.trim(),
      });
      setConnections((current) => [...current, created]);
      setProviderConnectionId(created.id);
      setConnectionMode("saved");
      setNewApiKey("");
      return created.id;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      return null;
    } finally { setConnecting(false); }
  }

  async function handleSaveHarness() {
    setError("");
    const connectionId = await connectProvider();
    if (!connectionId && !apiKeySecretRef) return;
    const effectiveTools = knowledgeBaseIds.length && !toolAllowlist.includes("search_documents")
      ? [...toolAllowlist, "search_documents"] : toolAllowlist;
    const body = {
      harness_config: {
        runtime_engine: runtimeEngine,
        ...(agent?.agent_type === "workflow" ? { workflow: {
          graph_version: "research_v1", max_plan_steps: 5, max_retrieval_queries: 3,
          max_research_cycles: 2, max_repair_cycles: 1, approval_policy: "mcp_and_connectors",
        }} : {}),
        runtime_model: {
          provider,
          model_id: modelId,
          ...(connectionId ? { provider_connection_id: connectionId } : { api_key_secret_ref: apiKeySecretRef }),
          usage_tier: usageTier,
          temperature,
          max_tokens: maxTokens,
          timeout_ms: 300000,
        },
        prompt_guardrails: { role, goal, guardrail_profile: guardrailProfile, context_mode: contextMode },
        memory: { vector_memory_enabled: agent?.agent_type === "chat" && conversationMemory,
                  graph_memory_enabled: false, episodic_memory_enabled: false },
      },
      skill_id: skillId,
      input_schema_id: inputSchemaId || null,
      output_schema_id: outputSchemaId,
      tool_allowlist: effectiveTools,
      mcp_tool_allowlist: mcpToolAllowlist,
      connector_allowlist: connectorAllowlist,
      skill_allowlist: skillAllowlist,
      knowledge_base_ids: knowledgeBaseIds,
      retrieval_config: {
        mode: "hybrid", top_k: 6, max_per_document: 3,
        standard_context_tokens: 2500, free_context_tokens: 1200,
      },
    };
    try {
      const saved = draft
        ? await api.put<AgentVersion>(`/agents/${agentId}/versions/${draft.id}`, body)
        : await api.post<AgentVersion>(`/agents/${agentId}/versions`, body);
      setDraft(saved);
      setStep(1);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  async function handleAddTrigger() {
    const config = newTrigger.type === "schedule" ? { cron_expr: newTrigger.cron_expr } : {};
    const trigger = await api.post<AgentTrigger>(`/agents/${agentId}/triggers`, {
      name: newTrigger.name,
      type: newTrigger.type,
      config,
    });
    setTriggers([...triggers, trigger]);
    setNewTrigger({ name: "", type: "manual", cron_expr: "" });
  }

  async function toggleEvaluationGate() {
    if (!agent) return;
    const updated = await api.put<Agent>(`/agents/${agentId}`, {
      evaluation_gate_enabled: !agent.evaluation_gate_enabled,
    });
    setAgent(updated);
  }

  async function handlePublish() {
    if (!draft) return;
    setError("");
    try {
      await api.post(`/agents/${agentId}/versions/${draft.id}/publish`);
      router.push(`/agents/${agentId}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  if (loading || !agent) return <p className="page-loading">Loading…</p>;

  const outputSchemas = schemas.filter((s) => s.kind === "output");
  const inputSchemas = schemas.filter((s) => s.kind === "input");

  return (
    <div className="page agent-editor-page">
      <PageHero eyebrow="Agent builder" title={`Configure ${agent.name}`} description="Bind the model, instructions, schemas, tools, triggers, and release controls for this version." />
      <div className="wizard-steps">
        {STEPS.map((label, i) => (
          <button type="button" key={label} className={`wizard-step ${step === i ? "active" : ""}`} onClick={() => setStep(i)}>
            {i + 1}. {label}
          </button>
        ))}
      </div>
      {error && <p className="form-error">{error}</p>}

      {step === 0 && (
        <div className="card">
          <h3>Runtime Model</h3>
          {agent.agent_type === "workflow" && <div className="security-note"><span>◇</span><div>
            <strong>Durable LangGraph research workflow</strong>
            <p>Runs asynchronously through prepare, plan, retrieval, research, approval, draft, verification and finalization. MCP and connector calls always pause for approval.</p>
          </div></div>}
          <div className="field">
            <label>Runtime implementation</label>
            <div className="ds-segmented">
              <button type="button" className={runtimeEngine === "direct" ? "active" : ""}
                onClick={() => setRuntimeEngine("direct")}>Direct SDK</button>
              <button type="button" className={runtimeEngine === "langchain" ? "active" : ""}
                onClick={() => setRuntimeEngine("langchain")}>LangChain LCEL</button>
            </div>
            <small className="field-help">Changes orchestration code only. Provider pricing, budgets, tools and output contracts remain the same for this version.</small>
          </div>
          <div className="field">
            <label>Provider</label>
            <select value={provider} onChange={(e) => {
              setProvider(e.target.value as RuntimeModelConfig["provider"]);
              setProviderConnectionId("");
              setModels([]);
            }}>
              {providers.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}{item.free_tier_available ? " · free tier available" : " · billing may be required"}
                </option>
              ))}
            </select>
            <small className="field-help">{providers.find((item) => item.id === provider)?.notice}</small>
          </div>
          <div className="field">
            <label>Model ID</label>
            {models.length ? (
              <select value={modelId} onChange={(e) => setModelId(e.target.value)}>
                {models.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}
              </select>
            ) : (
              <input value={modelId} onChange={(e) => setModelId(e.target.value)}
                placeholder="Connect a provider to load compatible models" />
            )}
          </div>
          <div className="field">
            <div className="field-label-row">
              <label>Provider connection</label>
              <a className="field-action-link" href="/secrets" target="_blank" rel="noreferrer">
                Manage API keys ↗
              </a>
            </div>
            <div className="ds-segmented">
              <button type="button" className={connectionMode === "saved" ? "active" : ""}
                onClick={() => setConnectionMode("saved")}>Saved connection</button>
              <button type="button" className={connectionMode === "new" ? "active" : ""}
                onClick={() => setConnectionMode("new")}>Paste new key</button>
            </div>
            {connectionMode === "saved" ? (
              <select value={providerConnectionId} onChange={(e) => setProviderConnectionId(e.target.value)}>
                <option value="">— select a connection —</option>
                {connections.filter((item) => item.provider === provider).map((item) => (
                  <option key={item.id} value={item.id}>{item.display_name} · {item.validation_status}</option>
                ))}
              </select>
            ) : (
              <div className="stack-sm">
                <input value={connectionName} onChange={(e) => setConnectionName(e.target.value)}
                  placeholder="My Gemini free key" />
                <input type="password" autoComplete="new-password" value={newApiKey}
                  onChange={(e) => setNewApiKey(e.target.value)} placeholder="Paste API key once" />
                <small className="field-help">The backend validates and encrypts this key. It is never stored in the harness.</small>
              </div>
            )}
            {!providerConnectionId && apiKeySecretRef && (
              <small className="field-help">This draft currently uses legacy secret reference “{apiKeySecretRef}”.</small>
            )}
          </div>
          <div className="field checkbox-field">
            <label>
              <input type="checkbox" checked={usageTier === "free"}
                onChange={(e) => setUsageTier(e.target.checked ? "free" : "standard")} /> Free API key
            </label>
            <small className="field-help">Uses conservative call, tool, iteration, token and time budgets. Large tasks may return partial work.</small>
          </div>
          <div className="field">
            <label>Temperature</label>
            <input type="number" step={0.1} value={temperature} onChange={(e) => setTemperature(Number(e.target.value))} />
          </div>
          <div className="field">
            <label>Max tokens</label>
            <input type="number" value={maxTokens} onChange={(e) => setMaxTokens(Number(e.target.value))} />
          </div>

          <h3>Prompt & Guardrails</h3>
          <div className="field">
            <label>Role</label>
            <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="Bounded task executor" />
          </div>
          <div className="field">
            <label>Goal</label>
            <input value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Complete one task and return schema-valid JSON." />
          </div>
          <div className="field">
            <label>Guardrail profile</label>
            <input value={guardrailProfile} onChange={(e) => setGuardrailProfile(e.target.value)} />
          </div>
          <div className="field">
            <label>Context mode</label>
            <select value={contextMode} onChange={(e) => setContextMode(e.target.value as never)}>
              <option value="minimal">Minimal</option>
              <option value="standard">Standard</option>
              <option value="full">Full</option>
            </select>
          </div>
          <div className="field">
            <label>System prompt binding (skill)</label>
            <select value={skillId} onChange={(e) => setSkillId(e.target.value)}>
              <option value="">— select a skill —</option>
              {skills.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} (v{s.version})
                </option>
              ))}
            </select>
          </div>

          <h3>Task Schemas</h3>
          <div className="field">
            <label>Input schema registry (optional)</label>
            <select value={inputSchemaId} onChange={(e) => setInputSchemaId(e.target.value)}>
              <option value="">— none —</option>
              {inputSchemas.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Output schema registry</label>
            <select value={outputSchemaId} onChange={(e) => setOutputSchemaId(e.target.value)}>
              <option value="">— select —</option>
              {outputSchemas.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <h3>Platform Tools</h3>
          <div className="checkbox-list">
            {platformTools.map((tool) => (
              <label key={tool.name}>
                <input
                  type="checkbox"
                  checked={toolAllowlist.includes(tool.name)}
                  onChange={() => setToolAllowlist(toggleInList(toolAllowlist, tool.name))}
                />{" "}
                {tool.name} — {tool.description}
              </label>
            ))}
          </div>

          <h3>Knowledge Bases</h3>
          <p className="field-help">Bind up to five reusable bases to this version. Runs retrieve automatically and may search again with the document tool.</p>
          <div className="checkbox-list">
            {knowledgeBases.map((base) => (
              <label key={base.id}>
                <input type="checkbox" checked={knowledgeBaseIds.includes(base.id)}
                  disabled={!knowledgeBaseIds.includes(base.id) && knowledgeBaseIds.length >= 5}
                  onChange={() => {
                    const next = toggleInList(knowledgeBaseIds, base.id);
                    setKnowledgeBaseIds(next);
                    if (next.length && !toolAllowlist.includes("search_documents")) {
                      setToolAllowlist([...toolAllowlist, "search_documents"]);
                    }
                  }} /> {base.name} — {base.document_count} document{base.document_count === 1 ? "" : "s"}
                {base.document_count === 0 && <small className="field-help"> No indexed evidence is available yet.</small>}
              </label>
            ))}
            {!knowledgeBases.length && <p className="field-help">Create and index a knowledge base in Content Store first.</p>}
          </div>
          <small className="field-help">Hybrid retrieval returns up to 6 chunks with a {usageTier === "free" ? "1,200" : "2,500"}-token context budget.</small>

          {agent.agent_type === "chat" && <><h3>Conversation Memory</h3>
            <label className="checkbox-row"><input type="checkbox" checked={conversationMemory}
              onChange={(event) => setConversationMemory(event.target.checked)} />
              Remember previous messages in explicitly created conversation threads</label>
            <p className="field-help">Opt-in · pinned to this version · retained for 30 days. Older turns may be summarized with this model and consume provider quota.</p>
          </>}

          <h3>Allowed Skills</h3>
          <div className="checkbox-list">
            {skills.map((s) => (
              <label key={s.id}>
                <input
                  type="checkbox"
                  checked={skillAllowlist.includes(s.id)}
                  onChange={() => setSkillAllowlist(toggleInList(skillAllowlist, s.id))}
                />{" "}
                {s.name}
              </label>
            ))}
          </div>

          <h3>Allowed MCP Tools</h3>
          <div className="checkbox-list">
            {mcpTools.map((t) => (
              <label key={t.id}>
                <input
                  type="checkbox"
                  checked={mcpToolAllowlist.includes(t.id)}
                  onChange={() => setMcpToolAllowlist(toggleInList(mcpToolAllowlist, t.id))}
                />{" "}
                {t.serverName}:{t.tool_name}
              </label>
            ))}
          </div>

          <h3>Allowed Connectors</h3>
          <div className="checkbox-list">
            {connectors.map((c) => (
              <label key={c.id}>
                <input
                  type="checkbox"
                  checked={connectorAllowlist.includes(c.id)}
                  onChange={() => setConnectorAllowlist(toggleInList(connectorAllowlist, c.id))}
                />{" "}
                {c.name}
              </label>
            ))}
          </div>

          <button className="btn" onClick={handleSaveHarness} disabled={connecting} style={{ marginTop: "1rem" }}>
            {connecting ? "Validating key…" : "Save & Next →"}
          </button>
        </div>
      )}

      {step === 1 && (
        <div className="card">
          <h3>Triggers</h3>
          {triggers.map((t) => (
            <div className="card" key={t.id}>
              <strong>{t.name}</strong> — <span className="badge">{t.type}</span>{" "}
              {t.type === "api" && <code>/agents/{agentId}/versions/{draft?.id}/run</code>}
              {t.type === "schedule" && <code>{String(t.config.cron_expr)}</code>}
            </div>
          ))}
          <div className="field">
            <label>Name</label>
            <input value={newTrigger.name} onChange={(e) => setNewTrigger({ ...newTrigger, name: e.target.value })} />
          </div>
          <div className="field">
            <label>Type</label>
            <select value={newTrigger.type} onChange={(e) => setNewTrigger({ ...newTrigger, type: e.target.value as never })}>
              <option value="manual">manual</option>
              <option value="api">api</option>
              <option value="schedule">schedule</option>
            </select>
          </div>
          {newTrigger.type === "schedule" && (
            <div className="field">
              <label>Cron expression</label>
              <input
                placeholder="0 8 * * *"
                value={newTrigger.cron_expr}
                onChange={(e) => setNewTrigger({ ...newTrigger, cron_expr: e.target.value })}
              />
            </div>
          )}
          <button className="btn btn-secondary" onClick={handleAddTrigger}>
            + Add Trigger
          </button>
          <div style={{ marginTop: "1rem" }}>
            <button className="btn btn-secondary" onClick={() => setStep(0)}>
              ← Back
            </button>{" "}
            <button className="btn" onClick={() => setStep(2)}>
              Next →
            </button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="card">
          <h3>Evaluation Gate</h3>
          <label>
            <input type="checkbox" checked={agent.evaluation_gate_enabled} onChange={toggleEvaluationGate} /> Require
            a passing evaluation run before publishing
          </label>
          {!agent.evaluation_gate_enabled && (
            <p>Evaluation is disabled — publishing will not require an evaluation run until this is enabled.</p>
          )}
          <div style={{ marginTop: "1rem" }}>
            <button className="btn btn-secondary" onClick={() => setStep(1)}>
              ← Back
            </button>{" "}
            <button className="btn" onClick={() => setStep(3)}>
              Next →
            </button>
          </div>
        </div>
      )}

      {step === 3 && draft && (
        <div className="card">
          <h3>Review</h3>
          <p>
            <strong>AGENT</strong> {agent.name}
          </p>
          <p>
            <strong>TYPE</strong> {agent.agent_type}
          </p>
          <p>
            <strong>RUNTIME MODEL</strong> {provider} / {modelId}
          </p>
          <p>
            <strong>ALLOWED PLATFORM TOOLS</strong> {toolAllowlist.join(", ") || "none"}
          </p>
          <p>
            <strong>ALLOWED MCP</strong>{" "}
            {mcpTools.filter((t) => mcpToolAllowlist.includes(t.id)).map((t) => `${t.serverName}:${t.tool_name}`).join(", ") ||
              "none"}
          </p>
          <p>
            <strong>ALLOWED SKILLS</strong> {skills.filter((s) => skillAllowlist.includes(s.id)).map((s) => s.name).join(", ") || "none"}
          </p>
          <p>
            <strong>TRIGGERS</strong> {triggers.map((t) => t.type).join(", ") || "none"}
          </p>
          <p>
            <strong>EVALUATION GATE</strong> {agent.evaluation_gate_enabled ? "Enabled" : "Disabled"}
          </p>
          <div style={{ marginTop: "1rem" }}>
            <button className="btn btn-secondary" onClick={() => setStep(2)}>
              ← Back
            </button>{" "}
            <button className="btn" onClick={handlePublish}>
              🚀 Publish Agent
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
