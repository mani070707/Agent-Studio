"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/api";
import { ActivityEvent, streamEvents } from "@/lib/events";
import { MetricStrip, PageHero, StatusBadge } from "@/components/ui";

type Worker = { id:string; worker_type:string; instance_id:string; status:string; last_seen_at:string; heartbeat_age_seconds:number };
type Queue = { depth:number; oldest_seconds:number; failed:number; health:"healthy"|"warning"|"critical" };
type Summary = { health:"healthy"|"warning"|"critical"; queues:Record<string,Queue>; recent_failures:number; workers:Worker[]; generated_at:string };

export default function OperationsPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");
  async function refresh() {
    try {
      const [next, history] = await Promise.all([api.get<Summary>("/operations/summary"),
        api.get<{items:ActivityEvent[]}>("/events?limit=50")]);
      setSummary(next); setEvents(history.items.reverse()); setError("");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Operations API is unavailable");
    }
  }
  useEffect(() => { void refresh(); return streamEvents({ onConnection:setConnected, onEvent:(event) => {
    setEvents((current) => [event, ...current.filter((item) => item.id !== event.id)].slice(0, 100));
    void refresh();
  }}); }, []);
  if (!summary) return <div className="page"><PageHero eyebrow="Production observability" title="Operations"
    description="Live, replayable lifecycle events and deterministic service-health rules." />
    <div className="alert-box"><strong>Operations data is unavailable</strong><p>{error || "Connecting to the backend…"}</p>
      <button className="btn btn-secondary" onClick={() => void refresh()}>Retry</button></div></div>;
  const queues = Object.entries(summary.queues);
  return <div className="page"><PageHero eyebrow="Production observability" title="Operations"
    description="Live, replayable lifecycle events and deterministic service-health rules."
    actions={<StatusBadge tone={connected ? "success" : "warning"}>{connected ? "Live stream" : "Reconnecting"}</StatusBadge>} />
    {error && <p className="form-error alert-box">{error}</p>}
    <MetricStrip items={[{value:summary.health,label:"Overall health"},{value:queues.reduce((n,[,q])=>n+q.depth,0),label:"Queued jobs"},
      {value:summary.workers.filter((w)=>w.status!=="stale").length,label:"Healthy workers"},{value:summary.recent_failures,label:"Recent failures"}]} />
    <section className="ds-form-section"><h2>Queues</h2><div className="ds-card-grid">{queues.map(([name,q]) => <article className="ds-card" key={name}>
      <div className="ds-card-top"><strong>{name}</strong><StatusBadge tone={q.health==="healthy"?"success":q.health==="warning"?"warning":"danger"}>{q.health}</StatusBadge></div>
      <p>{q.depth} queued · oldest {q.oldest_seconds.toFixed(1)}s · {q.failed} failed</p></article>)}</div></section>
    <section className="ds-form-section"><h2>Workers</h2><div className="ds-card-grid">{summary.workers.map((worker)=><article className="ds-card" key={worker.id}>
      <div className="ds-card-top"><strong>{worker.worker_type}</strong><StatusBadge tone={worker.status==="stale"?"danger":"success"}>{worker.status}</StatusBadge></div>
      <p>#{worker.instance_id.slice(0,8)} · heartbeat {worker.heartbeat_age_seconds.toFixed(1)}s ago</p></article>)}</div></section>
    <section className="ds-form-section"><h2>Recent events</h2><div className="trace-timeline">{events.map((event)=><article key={event.id}><span>{event.id}</span><div>
      <strong>{event.resource_type} · {event.event_type}</strong><small>{event.resource_id.slice(0,12)} · {new Date(event.created_at).toLocaleString()}</small>
      <pre className="ds-code">{JSON.stringify(event.payload,null,2)}</pre></div></article>)}</div></section>
  </div>;
}
