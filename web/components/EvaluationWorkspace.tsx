"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { AgentVersion, ContentItem, EvaluationCase, EvaluationCaseResult, EvaluationDataset, EvaluationRun } from "@/lib/types";
import { EmptyState, StatusBadge } from "@/components/ui";
import { streamEvents } from "@/lib/events";

type Props = { agentId: string; versions: AgentVersion[] };
type RuntimeSummary = { runtime_engine: string; average_latency_ms: number; input_tokens: number;
  output_tokens: number; model_calls: number; orchestration_overhead_ms: number };
type Comparison = { deltas: Record<string, number>; regressions: string[]; baseline_runtime: RuntimeSummary;
  candidate_runtime: RuntimeSummary; runtime_deltas: Record<string, number>; behavioral_regression_case_ids: string[] };
const terminal = new Set(["passed", "failed"]);
const percent = (value?: number) => value === undefined ? "—" : `${Math.round(value * 100)}%`;

export default function EvaluationWorkspace({ agentId, versions }: Props) {
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([]);
  const [cases, setCases] = useState<Record<string, EvaluationCase[]>>({});
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [results, setResults] = useState<Record<string, EvaluationCaseResult[]>>({});
  const [documents, setDocuments] = useState<ContentItem[]>([]);
  const [selectedDataset, setSelectedDataset] = useState("");
  const [selectedVersion, setSelectedVersion] = useState(versions[0]?.id || "");
  const [datasetName, setDatasetName] = useState("");
  const [caseInput, setCaseInput] = useState("{}");
  const [caseOutput, setCaseOutput] = useState("{}");
  const [expectedDocuments, setExpectedDocuments] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [compare, setCompare] = useState<{ baseline: string; candidate: string }>({ baseline: "", candidate: "" });
  const [comparison, setComparison] = useState<Comparison | null>(null);

  async function load() {
    const [datasetRows, runRows] = await Promise.all([
      api.get<EvaluationDataset[]>(`/agents/${agentId}/evaluation-datasets`),
      api.get<EvaluationRun[]>(`/agents/${agentId}/evaluation-runs`),
    ]);
    setDatasets(datasetRows); setRuns(runRows);
    if (!selectedDataset && datasetRows[0]) setSelectedDataset(datasetRows[0].id);
  }

  useEffect(() => { load().catch((reason) => setError(String(reason))); }, [agentId]);
  useEffect(() => streamEvents({ resourceType: "evaluation",
    onEvent: () => void load().catch(() => undefined),
    onConnection: (connected) => { if (!connected && runs.some((run) => !terminal.has(run.status))) {
      window.setTimeout(() => void load().catch(() => undefined), 5000);
    } },
  }), [agentId]);
  useEffect(() => {
    if (!selectedDataset) return;
    api.get<EvaluationCase[]>(`/evaluation-datasets/${selectedDataset}/cases`).then((rows) => setCases((old) => ({ ...old, [selectedDataset]: rows })));
  }, [selectedDataset]);
  useEffect(() => {
    const version = versions.find((item) => item.id === selectedVersion);
    if (!version) return;
    Promise.all(version.knowledge_base_ids.map((id) => api.get<ContentItem[]>(`/knowledge-bases/${id}/content`)))
      .then((groups) => setDocuments(groups.flat().filter((item) => item.index_status === "indexed")));
  }, [selectedVersion, versions]);

  async function createDataset() {
    setError("");
    try {
      const row = await api.post<EvaluationDataset>(`/agents/${agentId}/evaluation-datasets`, { name: datasetName, description: "", threshold: .9, retrieval_recall_threshold: .8, citation_precision_threshold: 1, grounding_threshold: 1 });
      setDatasetName(""); setSelectedDataset(row.id); await load();
    } catch (reason) { setError(String(reason)); }
  }

  async function addCase() {
    setError("");
    try {
      await api.post(`/evaluation-datasets/${selectedDataset}/cases`, { input: JSON.parse(caseInput), expected_output: JSON.parse(caseOutput), compare_fields: [], expected_document_ids: expectedDocuments, expected_chunk_ids: [], retrieval_k: 6 });
      const rows = await api.get<EvaluationCase[]>(`/evaluation-datasets/${selectedDataset}/cases`);
      setCases((old) => ({ ...old, [selectedDataset]: rows })); setExpectedDocuments([]);
    } catch (reason) { setError(reason instanceof SyntaxError ? "Input and expected output must be valid JSON." : String(reason)); }
  }

  async function startEvaluation() {
    const row = await api.post<EvaluationRun>(`/agents/${agentId}/versions/${selectedVersion}/evaluate?dataset_id=${selectedDataset}`);
    setRuns((old) => [row, ...old]);
  }

  async function inspect(run: EvaluationRun) {
    const rows = await api.get<EvaluationCaseResult[]>(`/evaluation-runs/${run.id}/cases`);
    setResults((old) => ({ ...old, [run.id]: rows }));
  }

  async function compareRuns() {
    setComparison(await api.get<Comparison>(`/evaluation-runs/compare?baseline_id=${compare.baseline}&candidate_id=${compare.candidate}`));
  }

  const completedRuns = useMemo(() => runs.filter((run) => terminal.has(run.status)), [runs]);
  const selectedCases = cases[selectedDataset] || [];
  return <div className="ds-stack">
    <section className="ds-form-section"><h3>Golden datasets</h3><p className="section-copy">Label the evidence and structured output a good run should produce.</p>
      {error && <p className="form-error alert-box">{error}</p>}
      <div className="ds-toolbar"><input placeholder="Dataset name" value={datasetName} onChange={(event) => setDatasetName(event.target.value)} /><button className="btn" disabled={!datasetName.trim()} onClick={createDataset}>Create dataset</button></div>
      <div className="ds-segmented">{datasets.map((dataset) => <button className={selectedDataset === dataset.id ? "active" : ""} key={dataset.id} onClick={() => setSelectedDataset(dataset.id)}>{dataset.name}</button>)}</div>
    </section>

    {selectedDataset ? <section className="ds-form-section"><h3>Cases ({selectedCases.length})</h3>
      <div className="ds-form-grid"><div className="field"><label>Input JSON</label><textarea rows={5} value={caseInput} onChange={(event) => setCaseInput(event.target.value)} /></div><div className="field"><label>Expected output JSON</label><textarea rows={5} value={caseOutput} onChange={(event) => setCaseOutput(event.target.value)} /></div></div>
      <div className="field"><label>Expected evidence documents</label>{documents.length ? documents.map((document) => <label className="checkbox-row" key={document.id}><input type="checkbox" checked={expectedDocuments.includes(document.id)} onChange={() => setExpectedDocuments((old) => old.includes(document.id) ? old.filter((id) => id !== document.id) : [...old, document.id])} />{document.filename}</label>) : <small className="field-help">The selected version has no indexed documents.</small>}</div>
      <button className="btn btn-secondary" onClick={addCase}>Add labelled case</button>
      {selectedCases.map((item) => <div className="evaluation-row" key={item.id}><div><strong>Case #{item.id.slice(0, 8)}</strong><span>{item.expected_document_ids.length} expected document(s) · top {item.retrieval_k}</span></div></div>)}
    </section> : <EmptyState title="Create a golden dataset" description="A golden dataset records questions, expected evidence, and expected structured output." />}

    <section className="ds-form-section"><h3>Run evaluation</h3><div className="ds-form-grid"><div className="field"><label>Agent version</label><select value={selectedVersion} onChange={(event) => setSelectedVersion(event.target.value)}>{versions.map((version) => <option key={version.id} value={version.id}>v{version.version_number} · {version.is_published ? "published" : "draft"}</option>)}</select></div><div className="field"><label>Dataset</label><select value={selectedDataset} onChange={(event) => setSelectedDataset(event.target.value)}>{datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}</select></div></div><button className="btn" disabled={!selectedDataset || !selectedVersion || !selectedCases.length} onClick={startEvaluation}>Start durable evaluation</button></section>

    <section className="ds-form-section"><h3>Evaluation history</h3>{runs.length ? runs.map((run) => <div key={run.id}><div className="evaluation-row"><div><strong>#{run.id.slice(0, 8)} · {run.completed_cases}/{run.total_cases} cases</strong><span>Answer {percent(run.metrics.case_pass_rate)} · Retrieval {percent(run.metrics.recall)} · Citations {percent(run.metrics.citation_precision)}</span></div><div><StatusBadge tone={run.status === "passed" ? "success" : run.status === "failed" ? "danger" : "info"}>{run.status}</StatusBadge> <button className="btn btn-secondary" onClick={() => inspect(run)}>Inspect</button></div></div>{results[run.id]?.map((result) => <div className="ds-trace" key={result.id}><span>{result.status === "passed" ? "✓" : "!"}</span><div><strong>Case {result.evaluation_case_id.slice(0, 8)}</strong><p className="field-help">Recall {percent(result.metrics.recall)} · MRR {percent(result.metrics.mrr)} · nDCG {percent(result.metrics.ndcg)} · {result.latency_ms} ms</p>{result.field_mismatches.map((mismatch) => <pre className="ds-code" key={mismatch.field}>{mismatch.field}: expected {JSON.stringify(mismatch.expected)}, received {JSON.stringify(mismatch.actual)}</pre>)}</div></div>)}</div>) : <EmptyState title="No evaluations yet" description="Run this dataset against an agent version to establish a quality baseline." />}</section>

    {completedRuns.length >= 2 && <section className="ds-form-section"><h3>Compare versions</h3><div className="ds-form-grid"><select value={compare.baseline} onChange={(event) => setCompare({ ...compare, baseline: event.target.value })}><option value="">Baseline</option>{completedRuns.map((run) => <option value={run.id} key={run.id}>#{run.id.slice(0, 8)}</option>)}</select><select value={compare.candidate} onChange={(event) => setCompare({ ...compare, candidate: event.target.value })}><option value="">Candidate</option>{completedRuns.map((run) => <option value={run.id} key={run.id}>#{run.id.slice(0, 8)}</option>)}</select></div><button className="btn btn-secondary" disabled={!compare.baseline || !compare.candidate} onClick={compareRuns}>Compare</button>{comparison && <pre className="ds-code">{JSON.stringify(comparison, null, 2)}</pre>}</section>}
  </div>;
}
