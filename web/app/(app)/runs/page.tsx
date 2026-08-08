"use client";

import { useEffect, useMemo, useState } from "react";
import RunFailureCard from "@/components/RunFailureCard";
import { Drawer, EmptyState, MetricStrip, PageHero, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import type { Run, RunStep, WorkflowApproval, WorkflowGraph } from "@/lib/types";
import WorkflowGraphView from "@/components/WorkflowGraphView";

function engineLabel(engine: Run["runtime_engine"]) {
  return engine === "langgraph" ? "LangGraph" : engine === "langchain" ? "LangChain" : "Direct";
}

function tone(status: Run["status"]) {
  return status === "completed" ? "success" : status === "failed" ? "danger" : status === "running" ? "info" : "warning";
}

function duration(run: Run) {
  if (!run.started_at || !run.completed_at) return "—";
  const milliseconds = new Date(run.completed_at).getTime() - new Date(run.started_at).getTime();
  return milliseconds < 1000 ? `${milliseconds} ms` : `${(milliseconds / 1000).toFixed(1)} s`;
}

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Run | null>(null);
  const [steps, setSteps] = useState<RunStep[]>([]);
  const [graph, setGraph] = useState<WorkflowGraph | null>(null);
  const [approvals, setApprovals] = useState<WorkflowApproval[]>([]);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | Run["status"]>("all");

  useEffect(() => {
    api.get<Run[]>("/runs").then(setRuns).finally(() => setLoading(false));
  }, []);

  async function openRun(run: Run) {
    setSelected(run);
    setSteps([]);
    setGraph(null); setApprovals([]);
    setSteps(await api.get<RunStep[]>(`/runs/${run.id}/steps`));
    if (run.runtime_engine === "langgraph") {
      const [workflowGraph, workflowApprovals] = await Promise.all([
        api.get<WorkflowGraph>(`/runs/${run.id}/graph`),
        api.get<WorkflowApproval[]>(`/runs/${run.id}/approvals`),
      ]);
      setGraph(workflowGraph); setApprovals(workflowApprovals);
    }
  }

  const visible = useMemo(
    () => runs.filter((run) => (filter === "all" || run.status === filter) && run.id.toLowerCase().includes(query.toLowerCase())),
    [filter, query, runs],
  );

  return (
    <div className="page">
      <PageHero eyebrow="Observability" title="Runs" description="Monitor agent executions, inspect grounded output, and follow every retrieval and tool step." />
      <MetricStrip items={[
        { value: runs.length, label: "Total runs" },
        { value: runs.filter((run) => run.status === "completed").length, label: "Completed" },
        { value: runs.filter((run) => run.status === "failed").length, label: "Failed" },
        { value: runs.filter((run) => run.grounding_status === "grounded").length, label: "Grounded" },
      ]} />

      <div className="ds-toolbar">
        <label className="ds-search"><span className="sr-only">Search runs</span><input placeholder="Search by run ID…" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
        <div className="ds-segmented">
          {(["all", "completed", "failed", "running"] as const).map((item) => <button key={item} className={filter === item ? "active" : ""} onClick={() => setFilter(item)}>{item[0].toUpperCase() + item.slice(1)}</button>)}
        </div>
      </div>

      {loading ? <div className="ds-skeleton-card" /> : visible.length ? (
        <div className="ds-table-wrap"><table className="ds-table"><thead><tr><th>Run</th><th>Engine</th><th>Status</th><th>Grounding</th><th>Duration</th><th>Completed</th><th /></tr></thead><tbody>
          {visible.map((run) => <tr key={run.id}>
            <td data-label="Run"><span className="ds-table-primary">#{run.id.slice(0, 8)}</span><span className="ds-table-sub">Version {run.agent_version_id.slice(0, 8)}</span></td>
            <td data-label="Engine">{engineLabel(run.runtime_engine)}</td>
            <td data-label="Status"><StatusBadge tone={tone(run.status)}>{run.status}</StatusBadge></td>
            <td data-label="Grounding">{run.grounding_status ? <StatusBadge tone={run.grounding_status === "grounded" ? "success" : "warning"}>{run.grounding_status.replaceAll("_", " ")}</StatusBadge> : "—"}</td>
            <td data-label="Duration">{duration(run)}</td>
            <td data-label="Completed">{run.completed_at ? new Date(run.completed_at).toLocaleString() : "—"}</td>
            <td data-label="Actions"><button className="btn btn-secondary" onClick={() => openRun(run)}>Inspect</button></td>
          </tr>)}
        </tbody></table></div>
      ) : <EmptyState icon="▶" title={query ? "No matching runs" : "No runs yet"} description={query ? "Try another run ID or status filter." : "Run an agent in the Playground and its execution trace will appear here."} />}

      <Drawer open={!!selected} title={`Run #${selected?.id.slice(0, 8) || ""}`} subtitle="Execution trace" onClose={() => setSelected(null)}>
        {selected && <>
          <div className="run-detail-summary"><StatusBadge tone={tone(selected.status)}>{selected.status}</StatusBadge><span>{duration(selected)}</span></div>
          <h3>Input</h3><pre className="ds-code">{JSON.stringify(selected.input, null, 2)}</pre>
          {selected.output?.failure ? <RunFailureCard failure={selected.output.failure} partial={selected.output.partial_output} /> : selected.output && <><h3>Output</h3><pre className="ds-code">{JSON.stringify(selected.output, null, 2)}</pre></>}
          <h3>Runtime</h3><p className="field-help">{engineLabel(selected.runtime_engine)}</p><pre className="ds-code">{JSON.stringify(selected.runtime_stats, null, 2)}</pre>
          {graph && <WorkflowGraphView graph={graph} approvals={approvals} />}
          {selected.grounding_status && <><h3>Grounding</h3><p className="field-help">{selected.grounding_status === "grounded" ? "The answer is supported by retrieved evidence." : "The bound knowledge bases did not contain enough evidence for a supported answer."}</p></>}
          {!!selected.citations?.length && <><h3>Verified sources</h3><div className="ds-stack">
            {selected.citations.map((citation) => <article className="ds-card" key={citation.source_id}>
              <strong>{citation.source_id} · {citation.filename}</strong>
              <p className="field-help">{citation.page_start ? `Pages ${citation.page_start}${citation.page_end && citation.page_end !== citation.page_start ? `–${citation.page_end}` : ""} · ` : ""}Similarity {citation.score.toFixed(3)}</p>
              {citation.excerpt && <p>{citation.excerpt}</p>}
            </article>)}
          </div></>}
          <h3>Trace</h3>
          {steps.length ? steps.map((step) => <div className="ds-trace" key={step.step_num}><span>{step.step_num}</span><div><strong>{step.type.replaceAll("_", " ")}</strong><pre className="ds-code">{JSON.stringify(step.detail, null, 2)}</pre></div></div>) : <p className="field-help">Loading trace…</p>}
        </>}
      </Drawer>
    </div>
  );
}
