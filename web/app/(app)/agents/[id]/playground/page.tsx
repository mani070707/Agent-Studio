"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { Agent, AgentVersion, Run, RunPreflight, RunStep } from "@/lib/types";
import { PageHero, StatusBadge } from "@/components/ui";
import RunFailureCard from "@/components/RunFailureCard";

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

  useEffect(() => {
    Promise.all([api.get<Agent>(`/agents/${agentId}`), api.get<AgentVersion[]>(`/agents/${agentId}/versions`)])
      .then(([agentData, versionData]) => {
        setAgent(agentData); setVersions(versionData);
        const preferred = versionData.find((version) => !version.is_published) || versionData[0];
        if (preferred) setVersionId(preferred.id);
      });
  }, [agentId]);

  async function handleRun(event: React.FormEvent) {
    event.preventDefault(); setError("");
    let input: Record<string, unknown>;
    try { input = JSON.parse(inputText); }
    catch { setError("Input must be valid JSON"); return; }
    setRunning(true); setRun(null); setSteps([]);
    try {
      const estimate = await api.post<RunPreflight>(`/agents/${agentId}/versions/${versionId}/run/preflight`, { input });
      setPreflight(estimate);
      const result = await api.post<Run>(`/agents/${agentId}/versions/${versionId}/run`, { input });
      setRun(result);
      setSteps(await api.get<RunStep[]>(`/runs/${result.id}/steps`));
    } catch (err) { setError(err instanceof ApiError ? err.message : String(err)); }
    finally { setRunning(false); }
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
              v{version.version_number} · {version.is_published ? "Published" : "Draft"}
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
          : run ? <pre className="playground-output">{JSON.stringify(run.output, null, 2)}</pre>
          : <div className="playground-placeholder"><span>◇</span><strong>No run yet</strong><p>Enter valid JSON to see the preflight and output.</p></div>}
      </section>
    </div>
    {run && <section className="trace-panel"><header><div><span>Execution trace</span><h2>{steps.length} recorded steps</h2></div>
      <code>#{run.id.slice(0, 8)}</code></header><div className="trace-timeline">
        {steps.map((step) => <article key={step.step_num}><span>{step.step_num}</span><div>
          <strong>{step.type.replaceAll("_", " ")}</strong><pre className="ds-code">{JSON.stringify(step.detail, null, 2)}</pre>
        </div></article>)}
      </div></section>}
  </div>;
}
