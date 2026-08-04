"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Skill } from "@/lib/types";
import { ConfirmDialog, Drawer, EmptyState, LoadingGrid, MetricStrip, PageHero, StatusBadge } from "@/components/ui";

const EMPTY = { name: "", system_prompt: "", user_prompt_template: "" };

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]), [form, setForm] = useState(EMPTY);
  const [error, setError] = useState(""), [loading, setLoading] = useState(true), [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false), [deleting, setDeleting] = useState<Skill | null>(null);
  async function load() { setLoading(true); setSkills(await api.get<Skill[]>("/skills")); setLoading(false); }
  useEffect(() => { load(); }, []);
  async function handleCreate(e: React.FormEvent) { e.preventDefault(); setError(""); try { await api.post("/skills", form); setForm(EMPTY); setCreating(false); await load(); } catch (err) { setError(err instanceof ApiError ? err.message : String(err)); } }
  async function handlePublish(id: string) { await api.post(`/skills/${id}/publish`); await load(); }
  async function handleDelete() { if (!deleting) return; await api.del(`/skills/${deleting.id}`); setDeleting(null); await load(); }
  const visible = useMemo(() => skills.filter((skill) => [skill.name,skill.system_prompt,skill.user_prompt_template].join(" ").toLowerCase().includes(query.toLowerCase())), [query,skills]);
  const published = skills.filter((skill) => skill.is_published).length;
  return <div className="page">
    <PageHero eyebrow="Prompt library" title="Skills" description="Reusable instructions that define how your agents think, respond, and complete tasks." actions={<button className="btn" onClick={() => setCreating(true)}>+ New skill</button>} />
    <MetricStrip items={[{value:skills.length,label:"Total skills"},{value:published,label:"Published"},{value:skills.length-published,label:"Drafts"}]} />
    <div className="ds-toolbar"><label className="ds-search"><span className="sr-only">Search skills</span><input placeholder="Search skills and prompts…" value={query} onChange={(e) => setQuery(e.target.value)} /></label></div>
    {loading ? <LoadingGrid /> : visible.length ? <div className="ds-card-grid">{visible.map((skill) => <article className="ds-resource-card" key={skill.id}><div className="ds-card-top"><span className="ds-card-icon">✦</span><StatusBadge tone={skill.is_published ? "success" : "warning"}>{skill.is_published ? "published" : "draft"}</StatusBadge></div><h3>{skill.name}</h3><span className="ds-card-meta">Version {skill.version}</span><p>{skill.system_prompt}</p><div className="ds-card-actions">{!skill.is_published && <button className="btn btn-secondary" onClick={() => handlePublish(skill.id)}>Publish</button>}<button className="btn btn-danger" onClick={() => setDeleting(skill)}>Delete</button></div></article>)}</div> : <EmptyState icon="✦" title={query ? "No matching skills" : "Build your prompt library"} description={query ? "Try a broader search." : "Create reusable instructions for agents and publish them when they are ready."} action={!query && <button className="btn" onClick={() => setCreating(true)}>Create skill</button>} />}
    <Drawer open={creating} title="Create skill" subtitle="Prompt library" onClose={() => setCreating(false)} footer={<><button className="btn btn-secondary" onClick={() => setCreating(false)}>Cancel</button><button className="btn" form="create-skill" type="submit">Create skill</button></>}><form id="create-skill" onSubmit={handleCreate}>{error && <p className="form-error">{error}</p>}<div className="field"><label>Name</label><input required placeholder="Customer support triage" value={form.name} onChange={(e) => setForm({...form,name:e.target.value})} /></div><div className="field"><label>System prompt</label><textarea required rows={7} value={form.system_prompt} onChange={(e) => setForm({...form,system_prompt:e.target.value})} /></div><div className="field"><label>User prompt template</label><textarea required rows={7} value={form.user_prompt_template} onChange={(e) => setForm({...form,user_prompt_template:e.target.value})} /><small className="field-help">Use {"{{variable}}"} placeholders for run input.</small></div></form></Drawer>
    <ConfirmDialog open={!!deleting} title="Delete this skill?" description="Agents referencing this skill may no longer be editable. This action cannot be undone." onClose={() => setDeleting(null)} onConfirm={handleDelete} />
  </div>;
}
