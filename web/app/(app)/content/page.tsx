"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { ContentItem, KnowledgeBase } from "@/lib/types";
import { ConfirmDialog, Drawer, EmptyState, LoadingGrid, MetricStrip, PageHero, StatusBadge } from "@/components/ui";

type Filter = "active" | "archived";

export default function ContentStorePage() {
  const [filter, setFilter] = useState<Filter>("active");
  const [bases, setBases] = useState<KnowledgeBase[]>([]);
  const [selected, setSelected] = useState<KnowledgeBase | null>(null);
  const [documents, setDocuments] = useState<ContentItem[]>([]);
  const [editing, setEditing] = useState<KnowledgeBase | "new" | null>(null);
  const [form, setForm] = useState({ name: "", description: "" });
  const [uploading, setUploading] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [archiving, setArchiving] = useState<KnowledgeBase | null>(null);
  const [deletingDocument, setDeletingDocument] = useState<ContentItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadBases = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setBases(await api.get<KnowledgeBase[]>(`/knowledge-bases?status=${filter}`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { void loadBases(); }, [loadBases]);

  async function openBase(base: KnowledgeBase) {
    setSelected(base);
    setDocuments([]);
    setError("");
    try {
      setDocuments(await api.get<ContentItem[]>(`/knowledge-bases/${base.id}/content`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  function openEditor(base: KnowledgeBase | "new") {
    setEditing(base);
    setForm(base === "new" ? { name: "", description: "" } : { name: base.name, description: base.description });
    setError("");
  }

  async function saveBase(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      if (editing === "new") await api.post("/knowledge-bases", form);
      else if (editing) await api.put(`/knowledge-bases/${editing.id}`, form);
      setEditing(null);
      await loadBases();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  async function archiveBase() {
    if (!archiving) return;
    try {
      await api.del(`/knowledge-bases/${archiving.id}`);
      setArchiving(null);
      setSelected(null);
      await loadBases();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  async function uploadDocument(event: FormEvent) {
    event.preventDefault();
    if (!selected || !file) return;
    const data = new FormData();
    data.append("file", file);
    setUploading(true);
    setError("");
    try {
      await api.post(`/content?knowledge_base_id=${selected.id}`, data);
      setFile(null);
      setUploadOpen(false);
      await openBase({ ...selected, document_count: selected.document_count + 1 });
      await loadBases();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  }

  async function deleteDocument() {
    if (!deletingDocument || !selected) return;
    try {
      await api.del(`/content/${deletingDocument.id}`);
      setDeletingDocument(null);
      await openBase({ ...selected, document_count: Math.max(0, selected.document_count - 1) });
      await loadBases();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  const documentTotal = bases.reduce((sum, base) => sum + base.document_count, 0);

  return <div className="page">
    <PageHero eyebrow="Reusable knowledge" title="Content Store" description="Organize trusted documents into knowledge bases that can later be shared across agent versions." actions={<button className="btn" onClick={() => openEditor("new")}>+ New knowledge base</button>} />
    <MetricStrip items={[{ value: bases.length, label: `${filter === "active" ? "Active" : "Archived"} bases` }, { value: documentTotal, label: "Documents" }, { value: "Tenant private", label: "Access" }]} />
    <div className="security-note"><span>i</span><div><strong>Foundation milestone</strong><p>Files are organized and tenant-isolated now. Embeddings, vector search, citations, and agent bindings arrive in later milestones.</p></div></div>
    <div className="ds-toolbar"><div className="ds-segmented">{(["active", "archived"] as Filter[]).map(value => <button key={value} className={filter === value ? "active" : ""} onClick={() => { setSelected(null); setFilter(value); }}>{value[0].toUpperCase() + value.slice(1)}</button>)}</div></div>
    {error && !editing && !uploadOpen && <p className="form-error alert-box">{error}</p>}
    {loading ? <LoadingGrid /> : bases.length ? <div className="ds-card-grid">{bases.map(base => <article className="ds-resource-card" key={base.id}>
      <div className="ds-card-top"><span className="ds-card-icon">K</span><StatusBadge tone={base.status === "active" ? "success" : "neutral"}>{base.status}</StatusBadge></div>
      <h3>{base.name}</h3><span className="ds-card-meta">{base.document_count} document{base.document_count === 1 ? "" : "s"}</span>
      <p>{base.description || "Reusable private knowledge for your agents."}</p>
      <div className="ds-card-actions"><button className="btn btn-secondary" onClick={() => openBase(base)}>Open</button>{base.status === "active" && <><button className="btn btn-secondary" onClick={() => openEditor(base)}>Edit</button><button className="btn btn-danger" onClick={() => setArchiving(base)}>Archive</button></>}</div>
    </article>)}</div> : <EmptyState icon="K" title={filter === "active" ? "Create your first knowledge base" : "No archived knowledge bases"} description={filter === "active" ? "Group related policies, manuals, notes, and reference documents into a reusable collection." : "Archived bases remain available here without deleting their documents."} action={filter === "active" ? <button className="btn" onClick={() => openEditor("new")}>Create knowledge base</button> : undefined} />}

    <Drawer open={!!editing} title={editing === "new" ? "Create knowledge base" : "Edit knowledge base"} subtitle="Reusable knowledge" onClose={() => setEditing(null)} footer={<><button className="btn btn-secondary" onClick={() => setEditing(null)}>Cancel</button><button className="btn" form="knowledge-base-form" type="submit">Save</button></>}>
      <form id="knowledge-base-form" onSubmit={saveBase}>{error && <p className="form-error">{error}</p>}<div className="field"><label>Name</label><input required maxLength={160} value={form.name} onChange={event => setForm({ ...form, name: event.target.value })} placeholder="Product manuals" /></div><div className="field"><label>Description</label><textarea rows={5} value={form.description} onChange={event => setForm({ ...form, description: event.target.value })} placeholder="What belongs in this knowledge base?" /></div></form>
    </Drawer>

    <Drawer open={!!selected && !uploadOpen} title={selected?.name || "Knowledge base"} subtitle={`${selected?.document_count || 0} documents`} onClose={() => setSelected(null)} footer={selected?.status === "active" ? <button className="btn" onClick={() => { setFile(null); setUploadOpen(true); }}>+ Upload document</button> : undefined}>
      {selected?.status === "archived" && <p className="field-help">Archived knowledge bases are read-only. Their documents have not been deleted.</p>}
      {documents.length ? <div className="ds-table-wrap"><table className="ds-table"><thead><tr><th>Document</th><th>Compatibility</th><th></th></tr></thead><tbody>{documents.map(document => <tr key={document.id}><td data-label="Document"><span className="ds-table-primary">{document.filename}</span></td><td data-label="Compatibility">{document.agent_id ? "Legacy agent linked" : "Knowledge base only"}</td><td data-label="Actions"><div className="ds-table-actions">{selected?.status === "active" && <button className="btn btn-danger" onClick={() => setDeletingDocument(document)}>Delete</button>}</div></td></tr>)}</tbody></table></div> : <EmptyState icon="↥" title="No documents yet" description="Upload a PDF or text document. Agent retrieval will be connected in a later milestone." />}
    </Drawer>

    <Drawer open={uploadOpen} title="Upload document" subtitle={selected?.name || "Knowledge base"} onClose={() => setUploadOpen(false)} footer={<><button className="btn btn-secondary" onClick={() => setUploadOpen(false)}>Cancel</button><button className="btn" form="upload-content" type="submit" disabled={!file || uploading}>{uploading ? "Uploading…" : "Upload"}</button></>}>
      <form id="upload-content" onSubmit={uploadDocument}>{error && <p className="form-error">{error}</p>}<label className="upload-dropzone"><span>↥</span><strong>{file ? file.name : "Choose a PDF or text file"}</strong><small>This compatibility path extracts text immediately; it does not create embeddings yet.</small><input type="file" accept=".pdf,.txt,text/plain,application/pdf" onChange={event => setFile(event.target.files?.[0] || null)} /></label></form>
    </Drawer>

    <ConfirmDialog open={!!archiving} title="Archive this knowledge base?" description="It becomes read-only, but its documents and storage objects are preserved." confirmLabel="Archive" onClose={() => setArchiving(null)} onConfirm={archiveBase} />
    <ConfirmDialog open={!!deletingDocument} title="Delete this document?" description="The file and its metadata will be permanently removed." onClose={() => setDeletingDocument(null)} onConfirm={deleteDocument} />
  </div>;
}
