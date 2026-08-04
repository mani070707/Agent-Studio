"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Agent } from "@/lib/types";
import { EmptyState, LoadingGrid, MetricStrip, PageHero, StatusBadge } from "@/components/ui";

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "active" | "draft">("all");

  useEffect(() => { api.get<Agent[]>("/agents").then(setAgents).finally(() => setLoading(false)); }, []);
  const visible = useMemo(() => agents.filter((agent) => (filter === "all" || agent.status === filter) && [agent.name, agent.description, agent.domain, agent.owner, ...agent.tags].join(" ").toLowerCase().includes(query.toLowerCase())), [agents, filter, query]);
  const active = agents.filter((agent) => agent.status === "active").length;

  return <div className="page">
    <PageHero eyebrow="Agent workspace" title="Agents" description="Design, test, and publish reliable AI agents for repeatable work." actions={<Link className="btn" href="/agents/new">+ New agent</Link>} />
    <MetricStrip items={[{value:agents.length,label:"Total agents"},{value:active,label:"Active"},{value:agents.length-active,label:"Drafts"},{value:new Set(agents.map((a) => a.domain).filter(Boolean)).size,label:"Domains"}]} />
    <div className="ds-toolbar"><label className="ds-search"><span className="sr-only">Search agents</span><input placeholder="Search agents, domains, or owners…" value={query} onChange={(e) => setQuery(e.target.value)} /></label><div className="ds-segmented">{(["all","active","draft"] as const).map((item) => <button key={item} className={filter === item ? "active" : ""} onClick={() => setFilter(item)}>{item[0].toUpperCase()+item.slice(1)}</button>)}</div></div>
    {loading ? <LoadingGrid count={6} /> : visible.length ? <div className="ds-card-grid">{visible.map((agent) => <Link className="ds-resource-card" key={agent.id} href={`/agents/${agent.id}`}><div className="ds-card-top"><span className="ds-card-icon">A</span><StatusBadge tone={agent.status === "active" ? "success" : "warning"}>{agent.status}</StatusBadge></div><h3>{agent.name}</h3><span className="ds-card-meta">{agent.agent_type} · {agent.domain || "General"}{agent.owner ? ` · ${agent.owner}` : ""}</span><p>{agent.description || "No description added yet."}</p><span className="tool-card-link">Open agent <b>→</b></span></Link>)}</div> : <EmptyState icon="A" title={query ? "No matching agents" : "Create your first agent"} description={query ? "Try a different search or status filter." : "Start with a purpose, then configure its model, skills, tools, and output."} action={!query && <Link className="btn" href="/agents/new">Create agent</Link>} />}
  </div>;
}
