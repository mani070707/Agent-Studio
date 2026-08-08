"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Agent, AgentVersion, ConversationMessage, ConversationThread, ConversationTurnResponse } from "@/lib/types";
import { EmptyState, PageHero, StatusBadge } from "@/components/ui";

export default function ConversationsPage() {
  const [threads, setThreads] = useState<ConversationThread[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [versions, setVersions] = useState<AgentVersion[]>([]);
  const [agentId, setAgentId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [selected, setSelected] = useState<ConversationThread | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [memoryNote, setMemoryNote] = useState("");
  const [error, setError] = useState("");

  async function loadThreads() { setThreads(await api.get<ConversationThread[]>("/conversations")); }
  useEffect(() => {
    Promise.all([loadThreads(), api.get<Agent[]>("/agents").then((rows) => setAgents(rows.filter((a) => a.agent_type === "chat")))])
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)));
  }, []);
  useEffect(() => {
    if (!agentId) { setVersions([]); setVersionId(""); return; }
    api.get<AgentVersion[]>(`/agents/${agentId}/versions`).then((rows) => {
      const eligible = rows.filter((v) => v.harness_config.memory?.vector_memory_enabled);
      setVersions(eligible); setVersionId(eligible[0]?.id || "");
    });
  }, [agentId]);

  async function openThread(thread: ConversationThread) {
    setSelected(thread); setMemoryNote("");
    setMessages(await api.get<ConversationMessage[]>(`/conversations/${thread.id}/messages`));
  }
  async function createThread() {
    if (!agentId || !versionId) return;
    const row = await api.post<ConversationThread>(`/agents/${agentId}/versions/${versionId}/conversations`, { title: "New conversation" });
    await loadThreads(); await openThread(row);
  }
  async function send(event: React.FormEvent) {
    event.preventDefault(); if (!selected || !message.trim()) return;
    const text = message.trim(); setMessage(""); setSending(true); setError("");
    try {
      const result = await api.post<ConversationTurnResponse>(`/conversations/${selected.id}/messages`, { message: text, variables: {} });
      setMessages((current) => [...current, ...result.messages]);
      setMemoryNote(result.memory.summarized
        ? `Older turns were summarized. ${result.memory.context_tokens} memory tokens were supplied.`
        : `${result.memory.context_tokens} memory tokens were supplied.`);
      await loadThreads();
    } catch (err) { setError(err instanceof ApiError ? err.message : String(err)); setMessage(text); }
    finally { setSending(false); }
  }
  async function clearMemory() {
    if (!selected || !window.confirm("Clear all remembered messages and the summary? Run audit records remain available.")) return;
    await api.post(`/conversations/${selected.id}/clear-memory`); setMessages([]); setMemoryNote("Memory cleared."); await loadThreads();
  }
  async function archive() {
    if (!selected) return;
    const row = await api.put<ConversationThread>(`/conversations/${selected.id}`, { status: "archived" });
    setSelected(row); await loadThreads();
  }
  async function rename() {
    if (!selected) return;
    const title = window.prompt("Conversation title", selected.title)?.trim();
    if (!title) return;
    const row = await api.put<ConversationThread>(`/conversations/${selected.id}`, { title });
    setSelected(row); await loadThreads();
  }
  async function remove() {
    if (!selected || !window.confirm("Delete this conversation and all remembered messages?")) return;
    await api.del(`/conversations/${selected.id}`); setSelected(null); setMessages([]); await loadThreads();
  }
  const selectedAgent = useMemo(() => agents.find((agent) => agent.id === selected?.agent_id), [agents, selected]);

  return <div className="page">
    <PageHero eyebrow="Short-term memory" title="Conversations" description="Continue chat-agent discussions with inspectable, version-pinned memory retained for 30 days." />
    {error && <p className="form-error alert-box">{error}</p>}
    <div className="playground-workspace">
      <section className="playground-panel"><header><div><span>Threads</span><h2>Conversation history</h2></div></header>
        <div className="field"><label>Chat agent</label><select value={agentId} onChange={(e) => setAgentId(e.target.value)}><option value="">Select…</option>{agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></div>
        <div className="field"><label>Memory-enabled version</label><select value={versionId} onChange={(e) => setVersionId(e.target.value)}><option value="">Select…</option>{versions.map((v) => <option key={v.id} value={v.id}>v{v.version_number}{v.is_published ? " · published" : " · draft"}</option>)}</select></div>
        <button className="btn" disabled={!versionId} onClick={createThread}>+ New conversation</button>
        <div className="ds-stack">{threads.map((thread) => <button className="ds-card" key={thread.id} onClick={() => openThread(thread)}><strong>{thread.title}</strong><span className="field-help">v{thread.agent_version_id.slice(0, 8)} · {thread.message_count} messages · {thread.message_token_count + thread.summary_token_count} tokens</span><StatusBadge tone={thread.status === "active" ? "success" : "neutral"}>{thread.status}</StatusBadge></button>)}</div>
      </section>
      <section className="playground-panel output-panel">{selected ? <>
        <header><div><span>{selectedAgent?.name || "Chat agent"}</span><h2>{selected.title}</h2></div><StatusBadge tone={selected.status === "active" ? "success" : "neutral"}>{selected.status}</StatusBadge></header>
        <p className="field-help">Pinned version {selected.agent_version_id.slice(0, 8)} · expires {new Date(selected.expires_at).toLocaleString()}</p>
        <div className="ds-stack">{messages.map((item) => <article className="ds-card" key={item.id}><strong>{item.role === "user" ? "You" : "Agent"}</strong><pre className="ds-code">{item.role === "user" ? item.content.text : JSON.stringify(item.content.output, null, 2)}</pre><small>{item.token_count} estimated tokens</small></article>)}</div>
        {!messages.length && <EmptyState icon="◇" title="No messages yet" description="Start this version-pinned conversation below." />}
        {memoryNote && <p className="field-help">{memoryNote}</p>}
        <form onSubmit={send}><div className="field"><label>Message</label><textarea required maxLength={16000} rows={4} value={message} onChange={(e) => setMessage(e.target.value)} disabled={selected.status !== "active"} /></div><button className="btn" disabled={sending || selected.status !== "active"}>{sending ? "Thinking…" : "Send"}</button></form>
        <div className="ds-card-actions"><button className="btn btn-secondary" onClick={rename}>Rename</button><button className="btn btn-secondary" onClick={clearMemory}>Clear memory</button>{selected.status === "active" && <button className="btn btn-secondary" onClick={archive}>Archive</button>}<button className="btn btn-danger" onClick={remove}>Delete</button></div>
        <p className="field-help">Clearing conversational memory does not delete separate run audit records.</p>
      </> : <EmptyState icon="◇" title="Select a conversation" description="Choose an existing thread or create one from a memory-enabled chat version." />}</section>
    </div>
  </div>;
}
