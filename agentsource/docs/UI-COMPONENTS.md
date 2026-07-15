# UI Components — AgentSource

Next.js + React + TypeScript. No CSS framework mandated — Tailwind is the default assumption below
but nothing here is Tailwind-specific. State management: no global store library required at this
scale — each screen owns its data via a typed API client (`ui/src/lib/api/*`) and local
`useState`/`useReducer`; only the Playground's live trace needs a reducer (see `LLD.md` §11).

---

## 1. Screens (`ui/src/screens/`)

| Screen | Route | Purpose |
|---|---|---|
| `DashboardPage` | `/` | Counts (agents, published versions, runs today) + recent runs list, links into everything else |
| `AgentsPage` | `/agents` | List agents, create new, open one |
| `AgentDetailPage` | `/agents/[id]` | Version history, draft editor entry point, publish button, evaluation tab |
| `AgentBuilderPage` | `/agents/[id]/build` | Wizard for creating/editing a draft version (see §2) |
| `PlaygroundPage` | `/playground` | Pick a published agent version, provide input (text or file upload), trigger a run, watch live trace, view result |
| `RunsPage` | `/runs` | All runs, filterable by agent/status |
| `RunDetailPage` | `/runs/[id]` | Full trace (post-hoc, non-streaming) + input/output |
| `SchemaRegistryPage` | `/schemas` | List/create/edit JSON schemas, with a schema preview/validator |
| `SkillsPage` | `/skills` | List/create/edit skill prompt bodies |
| `PromptLibraryPage` | `/prompts` | Standalone reusable prompt fragments, versioned |
| `McpToolsPage` | `/mcp-servers` | Register an MCP server, view its discovered tools |
| `ConnectorsPage` | `/connectors` | List/create connectors, test-call button |
| `WorkflowsPage` | `/workflows` | List workflows; Tier 1 step editor or Tier 2 BPMN canvas depending on which tier is enabled |
| `EvaluationsPage` | `/agents/[id]/evaluations` | Create/run evaluation datasets against an agent version, see score history |
| `SettingsPage` | `/settings` | `.env`-backed settings surfaced read-only (model provider, tier flag) + secret name management (never shows values) |

---

## 2. Agent Builder wizard (`AgentBuilderPage`)

A step wizard, not a single form — matches how the underlying data is actually structured
(harness config, skill, schema are separate entities being wired together, not one blob).

| Step | Component | Backend calls |
|---|---|---|
| 1. Basics | `AgentBasicsForm` | `POST /agents` |
| 2. Skill | `SkillPicker` (pick existing or "create new" inline, opens `SkillEditor`) | `GET /skills`, `POST /skills` |
| 3. Tools | `ToolAllowlistEditor` — three checklists: platform tools, MCP tools (grouped by server), connectors | `GET /tools/platform`, `GET /mcp-servers`, `GET /connectors` |
| 4. Output schema | `SchemaPicker` + `JsonSchemaEditor` (Monaco-based JSON editor with live validation against the JSON Schema meta-schema) | `GET /schemas`, `POST /schemas` |
| 5. Review & save | `HarnessConfigPreview` (renders the exact JSON that will be stored) + Save draft button | `POST /agents/{id}/versions` |

`AgentDetailPage` then shows a `VersionHistoryList` (each row: version number, published?, publish
button disabled/enabled based on `latestEvaluationStatus` from the agent detail response) and an
`EvaluationGateBanner` component that reads the same status and renders either a green "ready to
publish" state or an amber "needs a passing evaluation" state with a direct link to
`EvaluationsPage`.

---

## 3. Playground (`PlaygroundPage`)

| Component | Responsibility |
|---|---|
| `AgentVersionSelect` | Dropdown of published agent versions only |
| `RunInputForm` | Renders a form driven by the selected version's `inputSchemaId` (falls back to a raw JSON textarea + file upload if no input schema is set) |
| `TraceStreamViewer` | Opens `EventSource` on run trigger, renders each `RunTrace` event as it arrives as a timeline item (icon + label per `event_type`, expandable payload) |
| `RunResultViewer` | Renders `run.output` — generic JSON tree view by default; swappable for a domain-specific renderer (e.g. the bounding-box overlay described in the example agent) via a simple render-prop so the platform stays domain-agnostic |

`TraceStreamViewer` is the single most demo-worthy component — it's what turns "I called an LLM" into
"you can watch the agent work." Implement it before polishing anything else in the UI.

---

## 4. Registry pages (Schemas, Skills, Prompts, Connectors, MCP servers)

All five follow the same shape — a `RegistryListPage` layout component parameterized by resource:

```
RegistryListPage<T>
├── left: searchable list of T, "+ new" button
└── right: detail/edit panel for the selected item, Save/Delete
```

Build this once (`ui/src/components/registry/RegistryListPage.tsx`, generic over the resource's
list/detail/create API calls) and reuse it for all five registries rather than five bespoke pages —
they're structurally identical.

Resource-specific detail panels:
- `SchemaDetailPanel` → `JsonSchemaEditor` (Monaco + live meta-schema validation)
- `SkillDetailPanel` → plain multi-line text editor for the prompt body
- `PromptDetailPanel` → text editor + version history + publish button
- `ConnectorDetailPanel` → type-specific config form (REST: url/method/headers; queue: topic; llm_task: model settings) + "Test call" button wired to `POST /connectors/{id}/test`
- `McpServerDetailPanel` → server config form + read-only discovered-tools list + "Refresh tools" button

---

## 5. Workflows page

- Tier 1 (default): `StepListEditor` — an ordered list of steps, each "Run agent version X" or
  "Call connector Y," add/remove/reorder (drag handle optional, up/down buttons are enough).
- Tier 2 (if the BPMN engine upgrade is adopted): swap in a BPMN canvas library (e.g. `bpmn-js`)
  behind the same `WorkflowVersion` save/publish actions — the rest of the page (version list,
  publish button, run trigger) is identical between tiers.

---

## 6. Shared components (`ui/src/components/common/`)

| Component | Used by |
|---|---|
| `JsonSchemaEditor` | Schema registry, output/input schema pickers |
| `JsonTreeView` | Generic result viewer, trace payload viewer |
| `VersionHistoryList` | Agents, prompts, workflows |
| `PublishButton` | Agents, prompts, workflows — takes a `canPublish` boolean + reason, renders disabled state with tooltip when blocked |
| `StatusBadge` | Run status, evaluation status — small colored pill, consistent palette across the app |
| `EventSourceConnection` (hook: `useEventSource`) | Wraps `EventSource` lifecycle (connect/close/error/reconnect) — used only by `TraceStreamViewer` today but written generically since any future streaming view can reuse it |

---

## 7. Build order for the UI (pairs with `BUILD-PLAN.md`)

1. `RegistryListPage` + the five registries — establishes the API client pattern and generic
   list/detail UX once.
2. `AgentBuilderPage` wizard — the first place multiple registries get wired together.
3. `TraceStreamViewer` + `PlaygroundPage` — the centerpiece demo screen.
4. `EvaluationsPage` + `PublishButton`/`EvaluationGateBanner` — closes the authoring loop.
5. `DashboardPage`, `RunsPage`, `RunDetailPage`, `WorkflowsPage` — everything else, in roughly
   descending order of how often a reviewer would actually click into them during a demo.
