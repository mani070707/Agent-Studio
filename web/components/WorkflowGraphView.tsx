import type { WorkflowApproval, WorkflowGraph } from "@/lib/types";
import { StatusBadge } from "@/components/ui";

export default function WorkflowGraphView({ graph, approvals, onDecision }:
  { graph: WorkflowGraph; approvals: WorkflowApproval[]; onDecision?: (id: string, decision: "approve" | "reject") => void }) {
  return <div className="ds-stack">
    <section className="ds-form-section"><h3>Research graph · {graph.graph_version}</h3>
      <p className="field-help">Current node: <strong>{graph.current_node}</strong></p>
      <div className="ds-card-grid">{graph.nodes.map((node) => {
        const latest = node.events.at(-1); const status = latest?.status || "pending";
        return <article className="ds-card" key={node.id}><div className="ds-card-top"><strong>{node.id}</strong>
          <StatusBadge tone={status === "completed" ? "success" : status === "failed" ? "danger" : status === "running" ? "info" : "neutral"}>{status}</StatusBadge></div>
          {latest && <small>Attempt {latest.attempt}</small>}</article>;
      })}</div>
    </section>
    {approvals.map((approval) => <section className="ds-form-section" key={approval.id}><h3>External action approval</h3>
      <p><strong>{approval.tool_type}</strong> · {approval.tool_name}</p><pre className="ds-code">{JSON.stringify(approval.arguments, null, 2)}</pre>
      <small className="field-help">Arguments hash: {approval.arguments_hash.slice(0, 12)}…</small>
      {approval.status === "pending" && onDecision ? <div className="ds-card-actions"><button className="btn" onClick={() => onDecision(approval.id, "approve")}>Approve exact action</button><button className="btn btn-danger" onClick={() => onDecision(approval.id, "reject")}>Reject</button></div>
        : <StatusBadge tone={approval.status === "approved" ? "success" : "danger"}>{approval.status}</StatusBadge>}
    </section>)}
  </div>;
}
