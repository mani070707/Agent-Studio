"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { Agent, AgentVersion, Run, RunPreflight, RunStep, WorkflowApproval, WorkflowGraph } from "@/lib/types";
import { PageHero, StatusBadge } from "@/components/ui";
import RunFailureCard from "@/components/RunFailureCard";
import WorkflowGraphView from "@/components/WorkflowGraphView";
import { streamEvents } from "@/lib/events";

function tone(status: Run["status"]) {
  return status === "completed" ? "success" : status === "failed" ? "danger" : status === "running" ? "info" : "warning" as const;
}

export default function PlaygroundPage() {
  const { id: agentId } = useParams<{ id: string }>();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [versions, setVersions] = useState<AgentVersion[]>([]);
  const [versionId, setVersionId] = useState("");
  const [inputText, setInputText] = useState("{}");
  const [running, setRunning] = useState(false);
  const [run, setRun] = useState<Run | null>(null);
  const [steps, setSteps] = useState<RunStep[]>([]);
  const [preflight, setPreflight] = useState<RunPreflight | null>(null);
  const [error, setError] = useState("");
  const [graph, setGraph] = useState<WorkflowGraph | null>(null);
  const [approvals, setApprovals] = useState<WorkflowApproval[]>([]);
  const stopStream = useRef<null | (() => void)>(null);

  async function refreshWorkflow(runId: string) {
    const [nextRun, nextGraph, nextApprovals] = await Promise.all([
      api.get<Run>(`/runs/${runId}`),
      api.get<WorkflowGraph>(`/runs/${runId}/graph`),
      api.get<WorkflowApproval[]>(`/runs/${runId}/approvals`),
    ]);
    setRun(nextRun); setGraph(nextGraph); setApprovals(nextApprovals);
    if (!["queued", "running", "waiting_approval"].includes(nextRun.status)) {
      stopStream.current?.(); stopStream.current = null;
      setRunning(false);
      setSteps(await api.get<RunStep[]>(`/runs/${runId}/steps`));
    }
  }

  function watchWorkflow(runId: string) {
    stopStream.current?.();
    stopStream.current = streamEvents({ resourceType: "workflow", resourceId: runId,
      onEvent: () => void refreshWorkflow(runId),
      onConnection: (connected) => { if (!connected) window.setTimeout(() => void refreshWorkflow(runId), 5000); },
    });
  }

  async function decideApproval(approvalId: string, decision: "approve" | "reject") {
    if (!run) return;
    await api.post(`/runs/${run.id}/approvals/${approvalId}`, { decision });
    await refreshWorkflow(run.id);
  }

  useEffect(() => {
    Promise.all([api.get<Agent>(`/agents/${agentId}`), api.get<AgentVersion[]>(`/agents/${agentId}/versions`)])
      .then(([agentData, versionData]) => {
        setAgent(agentData); setVersions(versionData);
        const preferred = versionData.find((version) => !version.is_published) || versionData[0];
        if (preferred) setVersionId(preferred.id);
      });
  }, [agentId]);
  useEffect(() => () => stopStream.current?.(), []);

  async function handleRun(event: React.FormEvent) {
    event.preventDefault(); setError("");
    let input: Record<string, unknown>;
    try { input = JSON.parse(inputText); }
    catch { setError("Input must be valid JSON"); return; }
    setRunning(true); setRun(null); setSteps([]); setGraph(null); setApprovals([]);
    try {
      const estimate = await api.post<RunPreflight>(`/agents/${agentId}/versions/${versionId}/run/preflight`, { input });
      setPreflight(estimate);
      const result = await api.post<Run>(`/agents/${agentId}/versions/${versionId}/run`, { input });
      setRun(result);
      if (result.runtime_engine === "langgraph") { watchWorkflow(result.id); await refreshWorkflow(result.id); }
      else {
        setSteps(await api.get<RunStep[]>(`/runs/${result.id}/steps`));
        setRunning(false);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setRunning(false);
    }
  }

  if (!agent) return <p className="page-loading">Loading…</p>;
  const failure = run?.output?.failure;
  return <div className="page playground-page">
    <PageHero eyebrow="Test environment" title={`${agent.name} Playground`}
      description="Run a version, inspect its structured output, and follow the complete execution trace."
      actions={<Link className="btn btn-secondary" href={`/agents/${agentId}`}>← Agent details</Link>} />
    <div className="playground-workspace">
      <section className="playground-panel">
        <header><div><span>Input</span><h2>Test request</h2></div>
          <select value={versionId} onChange={(event) => setVersionId(event.target.value)}>
            {versions.map((version) => <option key={version.id} value={version.id}>
              v{version.version_number} · {version.is_published ? "Published" : "Draft"} · {version.harness_config.runtime_engine || "direct"}
            </option>)}
          </select></header>
        <form onSubmit={handleRun}>
          <label className="json-editor"><span>JSON input</span>
            <textarea value={inputText} onChange={(event) => setInputText(event.target.value)} spellCheck={false} />
          </label>
          {error && <p className="form-error">{error}</p>}
          {preflight?.usage_tier === "free" && <div className="free-mode-notice">
            <strong>Free-key safety mode</strong>
            <span>Estimated {preflight.estimated_input_tokens.toLocaleString()} input tokens · {preflight.likely_subtasks} likely subtasks.</span>
            {preflight.warnings.map((warning) => <span key={warning}>⚠ {warning}</span>)}
          </div>}
          <button className="btn run-button" type="submit" disabled={running || !versionId}>
            {running ? "Running agent…" : "▶ Run agent"}
          </button>
        </form>
      </section>
      <section className="playground-panel output-panel">
        <header><div><span>Result</span><h2>Structured output</h2></div>
          {run && <StatusBadge tone={tone(run.status)}>{run.status}</StatusBadge>}</header>
        {running ? <div className="playground-running"><i /><strong>Agent is working</strong><span>Calling the model and approved tools…</span></div>
          : failure ? <RunFailureCard failure={failure} partial={run?.output?.partial_output} />
          : run ? <><div className="security-note"><span>⚙</span><div><strong>{run.runtime_engine === "langgraph" ? "LangGraph workflow" : run.runtime_engine === "langchain" ? "LangChain LCEL" : "Direct SDK"}</strong><p>{run.runtime_stats.model_calls || 0} model calls · {(run.runtime_stats.input_tokens || 0) + (run.runtime_stats.output_tokens || 0)} tokens · {Math.round(run.runtime_stats.total_duration_ms || 0)} ms</p></div></div><pre className="playground-output">{JSON.stringify(run.output, null, 2)}</pre>
            {run.grounding_status && <div className="security-note"><span>i</span><div><strong>Grounding: {run.grounding_status.replaceAll("_", " ")}</strong><p>{run.citations.length ? `${run.citations.length} verified source citation${run.citations.length === 1 ? "" : "s"}.` : "The knowledge base did not contain sufficient evidence."}</p></div></div>}
            {run.citations.map(citation => <article className="ds-resource-card" key={citation.source_id}><div className="ds-card-top"><strong>{citation.source_id} · {citation.filename}</strong><StatusBadge tone="info">{(citation.score * 100).toFixed(1)}%</StatusBadge></div><p>{citation.excerpt}</p><small>{citation.page_start ? `Pages ${citation.page_start}–${citation.page_end}` : "Document excerpt"}</small></article>)}
          </>
          : <div className="playground-placeholder"><span>◇</span><strong>No run yet</strong><p>Enter valid JSON to see the preflight and output.</p></div>}
      </section>
    </div>
    {graph && <WorkflowGraphView graph={graph} approvals={approvals} onDecision={decideApproval} />}
    {run && <section className="trace-panel"><header><div><span>Execution trace</span><h2>{steps.length} recorded steps</h2></div>
      <code>#{run.id.slice(0, 8)}</code></header><div className="trace-timeline">
        {steps.map((step) => <article key={step.step_num}><span>{step.step_num}</span><div>
          <strong>{step.type.replaceAll("_", " ")}</strong><pre className="ds-code">{JSON.stringify(step.detail, null, 2)}</pre>
        </div></article>)}
      </div></section>}
  </div>;
}
