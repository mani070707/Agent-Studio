"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type {
  CatalogTool,
  CatalogToolSource,
  Connector,
  McpServer,
  McpTool,
  PlatformTool,
} from "@/lib/types";

type Filter = "all" | CatalogToolSource;

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All tools" },
  { value: "platform", label: "Built-in" },
  { value: "mcp", label: "MCP" },
  { value: "connector", label: "Connectors" },
];

function displayName(name: string) {
  return name
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function ToolGlyph({ source }: { source: CatalogToolSource }) {
  if (source === "mcp") {
    return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 7.5V6a4 4 0 0 1 8 0v1.5M6.5 10h11v9h-11zM9.5 14.5h5"/></svg>;
  }
  if (source === "connector") {
    return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 12h8M12 8v8M7 5H5a2 2 0 0 0-2 2v2M17 5h2a2 2 0 0 1 2 2v2M7 19H5a2 2 0 0 1-2-2v-2M17 19h2a2 2 0 0 0 2-2v-2"/></svg>;
  }
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14.7 6.3 3-3a4.2 4.2 0 0 1-5.4 5.4l-6.9 6.9a2.1 2.1 0 1 0 3 3l6.9-6.9a4.2 4.2 0 0 0 5.4-5.4l-3 3-3-3Z"/></svg>;
}

export default function ToolsPage() {
  const [tools, setTools] = useState<CatalogTool[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState<CatalogTool | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadCatalog() {
      setLoading(true);
      const nextTools: CatalogTool[] = [];
      const nextWarnings: string[] = [];

      const [platformResult, serversResult, connectorsResult] = await Promise.allSettled([
        api.get<PlatformTool[]>("/tools/platform"),
        api.get<McpServer[]>("/mcp-servers"),
        api.get<Connector[]>("/connectors"),
      ]);

      if (platformResult.status === "fulfilled") {
        nextTools.push(...platformResult.value.map((tool) => ({
          id: `platform:${tool.name}`,
          source: "platform" as const,
          name: displayName(tool.name),
          description: tool.description,
          status: tool.name === "search_documents" ? "Needs agent content" as const : "Available" as const,
          sourceLabel: "Built-in",
          inputSchema: tool.input_schema,
          outputSchema: tool.output_schema,
        })));
      } else {
        nextWarnings.push("Built-in tools could not be loaded.");
      }

      if (serversResult.status === "fulfilled") {
        const serverToolResults = await Promise.allSettled(
          serversResult.value.map(async (server) => ({
            server,
            tools: await api.get<McpTool[]>(`/mcp-servers/${server.id}/tools`),
          })),
        );
        serverToolResults.forEach((result, index) => {
          const server = serversResult.value[index];
          if (result.status === "rejected") {
            nextWarnings.push(`Tools from ${server.name} could not be loaded.`);
            return;
          }
          nextTools.push(...result.value.tools.map((tool) => ({
            id: `mcp:${server.id}:${tool.id}`,
            source: "mcp" as const,
            name: displayName(tool.tool_name),
            description: `Discovered from the ${server.name} MCP server.`,
            status: "Connected" as const,
            sourceLabel: server.name,
            inputSchema: tool.input_schema,
            outputSchema: tool.output_schema,
            setupHref: "/mcp-servers",
          })));
        });
      } else {
        nextWarnings.push("MCP servers could not be loaded.");
      }

      if (connectorsResult.status === "fulfilled") {
        nextTools.push(...connectorsResult.value.map((connector) => ({
          id: `connector:${connector.id}`,
          source: "connector" as const,
          name: connector.name,
          description: `REST connector for ${connector.base_url}`,
          status: "Configured" as const,
          sourceLabel: "REST connector",
          configuration: {
            base_url: connector.base_url,
            authentication: connector.auth_secret_ref ? "Credential configured" : "No credential",
            request_template: connector.request_template,
          },
          setupHref: "/connectors",
        })));
      } else {
        nextWarnings.push("REST connectors could not be loaded.");
      }

      if (!cancelled) {
        setTools(nextTools);
        setWarnings(nextWarnings);
        setLoading(false);
      }
    }

    loadCatalog();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!selected) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setSelected(null);
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [selected]);

  const counts = useMemo(() => ({
    all: tools.length,
    platform: tools.filter((tool) => tool.source === "platform").length,
    mcp: tools.filter((tool) => tool.source === "mcp").length,
    connector: tools.filter((tool) => tool.source === "connector").length,
  }), [tools]);

  const visibleTools = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return tools.filter((tool) => {
      const matchesFilter = filter === "all" || tool.source === filter;
      const matchesQuery = !normalizedQuery || [tool.name, tool.description, tool.sourceLabel]
        .some((value) => value.toLowerCase().includes(normalizedQuery));
      return matchesFilter && matchesQuery;
    });
  }, [filter, query, tools]);

  return (
    <div className="page tools-page">
      <div className="tools-hero">
        <div>
          <span className="eyebrow">Capability registry</span>
          <h1>Tools</h1>
          <p>Explore the built-in and connected capabilities available to your agents.</p>
        </div>
        <div className="tools-hero-actions">
          <Link className="btn btn-secondary" href="/mcp-servers">Configure MCP</Link>
          <Link className="btn" href="/connectors">Configure connector</Link>
        </div>
      </div>

      <div className="tool-stats" aria-label="Tool totals">
        <div><strong>{counts.all}</strong><span>Total tools</span></div>
        <div><strong>{counts.platform}</strong><span>Built-in</span></div>
        <div><strong>{counts.mcp}</strong><span>MCP tools</span></div>
        <div><strong>{counts.connector}</strong><span>Connectors</span></div>
      </div>

      {warnings.length > 0 && (
        <div className="catalog-warning" role="status">
          <strong>Some sources need attention.</strong>
          <span>{warnings.join(" ")}</span>
        </div>
      )}

      <div className="tools-controls">
        <label className="tool-search">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
          <span className="sr-only">Search tools</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search tools and integrations…" />
        </label>
        <div className="tool-filters" role="group" aria-label="Filter tools">
          {FILTERS.map((item) => (
            <button key={item.value} type="button" className={filter === item.value ? "active" : ""} onClick={() => setFilter(item.value)}>
              {item.label}<span>{counts[item.value]}</span>
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="tool-grid" aria-label="Loading tools">
          {[0, 1, 2, 3, 4, 5].map((item) => <div className="tool-card tool-card-skeleton" key={item} />)}
        </div>
      ) : visibleTools.length > 0 ? (
        <div className="tool-grid">
          {visibleTools.map((tool) => (
            <button type="button" className="tool-card" key={tool.id} onClick={() => setSelected(tool)}>
              <span className={`tool-card-icon source-${tool.source}`}><ToolGlyph source={tool.source} /></span>
              <span className="tool-card-content">
                <span className="tool-card-heading"><strong>{tool.name}</strong><i className={`tool-status status-${tool.source}`}>{tool.status}</i></span>
                <span className="tool-source">{tool.sourceLabel}</span>
                <span className="tool-description">{tool.description}</span>
                <span className="tool-card-link">View details <b>→</b></span>
              </span>
            </button>
          ))}
        </div>
      ) : (
        <div className="catalog-empty">
          <span className="catalog-empty-icon"><ToolGlyph source={filter === "all" ? "platform" : filter} /></span>
          <h2>{query ? "No matching tools" : `No ${FILTERS.find((item) => item.value === filter)?.label.toLowerCase()} yet`}</h2>
          <p>{query ? "Try another search or select a different category." : "Connect a source to make more capabilities available to your agents."}</p>
          {filter === "mcp" && <Link className="btn" href="/mcp-servers">Configure MCP server</Link>}
          {filter === "connector" && <Link className="btn" href="/connectors">Create connector</Link>}
        </div>
      )}

      {selected && (
        <div className="tool-drawer-layer" role="presentation">
          <button className="tool-drawer-backdrop" aria-label="Close tool details" onClick={() => setSelected(null)} />
          <aside className="tool-drawer" role="dialog" aria-modal="true" aria-labelledby="tool-detail-title">
            <div className="tool-drawer-header">
              <span className={`tool-card-icon source-${selected.source}`}><ToolGlyph source={selected.source} /></span>
              <div><span className="tool-source">{selected.sourceLabel}</span><h2 id="tool-detail-title">{selected.name}</h2></div>
              <button className="tool-drawer-close" type="button" aria-label="Close tool details" onClick={() => setSelected(null)}>×</button>
            </div>
            <div className="tool-drawer-body">
              <span className={`tool-status status-${selected.source}`}>{selected.status}</span>
              <p>{selected.description}</p>
              {selected.inputSchema && <SchemaBlock title="Input schema" value={selected.inputSchema} />}
              {selected.outputSchema && <SchemaBlock title="Output schema" value={selected.outputSchema} />}
              {selected.configuration && <SchemaBlock title="Connector configuration" value={selected.configuration} />}
            </div>
            {selected.setupHref && (
              <div className="tool-drawer-footer">
                <Link className="btn" href={selected.setupHref}>{selected.source === "mcp" ? "Manage MCP servers" : "Manage connectors"}</Link>
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}

function SchemaBlock({ title, value }: { title: string; value: Record<string, unknown> }) {
  return <section className="tool-schema"><h3>{title}</h3><pre>{JSON.stringify(value, null, 2)}</pre></section>;
}
