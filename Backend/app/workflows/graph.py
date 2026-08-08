import copy
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.connectors.executor import execute_connector
from app.core.secret_resolver import resolve_secret
from app.db.models import (AgentVersion, Connector, McpServer, McpTool, Run, WorkflowApproval,
                           WorkflowExecution, WorkflowNodeEvent)
from app.mcp_client.client import call_tool as call_mcp_tool
from app.modules.retrieval.service import EvidenceLedger, HybridRetriever
from app.modules.semantic.router import embedder as semantic_embedder
from app.runs.executor import build_run_prompts, execute_run
from app.observability.service import emit

NODES = ["prepare", "plan", "retrieve", "research", "approval", "draft", "verify", "repair", "finalize"]
EDGES = [("prepare", "plan"), ("plan", "retrieve"), ("retrieve", "research"),
         ("research", "approval"), ("research", "draft"), ("approval", "draft"),
         ("draft", "verify"), ("verify", "repair"), ("verify", "finalize"),
         ("repair", "draft"), ("finalize", "end")]


def redact_arguments(value):
    if isinstance(value, dict):
        return {key: ("[REDACTED]" if any(word in key.lower() for word in ("secret", "token", "password", "api_key"))
                      else redact_arguments(item)) for key, item in value.items()}
    if isinstance(value, list): return [redact_arguments(item) for item in value]
    return value


class ResearchState(TypedDict, total=False):
    run_id: str
    user_id: str
    version_id: str
    request: dict
    plan: list[str]
    evidence: list[dict]
    retrieval_stats: dict
    external_action: dict
    approval: dict
    tool_result: dict
    validation_errors: list[str]
    repair_count: int
    completed: bool


class WorkflowGraph:
    def __init__(self, db, checkpointer) -> None:
        self.db = db
        self.checkpointer = checkpointer

    def compile(self):
        graph = StateGraph(ResearchState)
        for name in NODES:
            graph.add_node(name, self._tracked(name, getattr(self, name)))
        graph.add_edge(START, "prepare")
        graph.add_edge("prepare", "plan")
        graph.add_edge("plan", "retrieve")
        graph.add_edge("retrieve", "research")
        graph.add_conditional_edges("research", lambda state: "approval" if state.get("external_action") else "draft",
                                    {"approval": "approval", "draft": "draft"})
        graph.add_edge("approval", "draft")
        graph.add_edge("draft", "verify")
        graph.add_conditional_edges("verify", self._after_verify,
                                    {"repair": "repair", "finalize": "finalize"})
        graph.add_edge("repair", "draft")
        graph.add_edge("finalize", END)
        return graph.compile(checkpointer=self.checkpointer)

    def _tracked(self, name, fn):
        def wrapped(state):
            execution = self.db.query(WorkflowExecution).filter(WorkflowExecution.run_id == state["run_id"]).one()
            execution.current_node = name
            execution.updated_at = datetime.now(timezone.utc)
            event = WorkflowNodeEvent(run_id=state["run_id"], user_id=state["user_id"], node=name,
                                      status="running", detail={})
            self.db.add(event)
            emit(self.db, user_id=state["user_id"], resource_type="workflow", resource_id=state["run_id"],
                 event_type="progress", payload={"node": name, "status": "running"})
            self.db.commit()
            try:
                result = fn(state)
                event.status = "completed"
                event.detail = self._summary(name, result)
                emit(self.db, user_id=state["user_id"], resource_type="workflow", resource_id=state["run_id"],
                     event_type="progress", payload={"node": name, "status": "completed",
                                                     "attempt": event.attempt})
                return result
            except Exception:
                event.status = "failed"
                raise
            finally:
                event.completed_at = datetime.now(timezone.utc)
                self.db.commit()
        return wrapped

    @staticmethod
    def _summary(node: str, result: dict) -> dict:
        if node == "retrieve":
            return {"sources": len(result.get("evidence", [])), "stats": result.get("retrieval_stats", {})}
        if node == "plan":
            return {"steps": result.get("plan", [])}
        if node == "approval":
            return {"decision": (result.get("approval") or {}).get("decision")}
        return {"completed": True}

    def prepare(self, state: ResearchState) -> dict:
        version = self._version(state)
        if not version or not isinstance(state.get("request"), dict):
            raise ValueError("Workflow input or version is unavailable")
        return {"repair_count": state.get("repair_count", 0)}

    def plan(self, state: ResearchState) -> dict:
        text = json.dumps(state["request"], ensure_ascii=False)[:4000]
        parts = [part.strip(" -") for part in text.replace("\\n", "\n").splitlines() if part.strip()]
        return {"plan": (["Understand the requested outcome", "Retrieve bound evidence"] + parts[:3])[:5]}

    def retrieve(self, state: ResearchState) -> dict:
        version = self._version(state)
        _, query = build_run_prompts(version, state["request"])
        ledger = EvidenceLedger()
        config = version.retrieval_config or {}
        evidence, stats = HybridRetriever(self.db, semantic_embedder()).retrieve(
            version.id, state["user_id"], query, top_k=int(config.get("top_k", 6)),
            max_per_document=int(config.get("max_per_document", 3)),
            token_budget=int(config.get("standard_context_tokens", 2500)), ledger=ledger)
        return {"evidence": [item.citation() for item in evidence], "retrieval_stats": stats}

    def research(self, state: ResearchState) -> dict:
        action = state["request"].get("external_action")
        if not isinstance(action, dict) or action.get("tool_type") not in {"connector", "mcp"}:
            return {"external_action": {}}
        version = self._version(state)
        allowed = (version.connector_allowlist if action["tool_type"] == "connector"
                   else version.mcp_tool_allowlist)
        if str(action.get("tool_id", "")) not in allowed:
            raise ValueError("The requested external tool is not allowed by this agent version")
        return {"external_action": {"tool_type": action["tool_type"], "tool_id": str(action.get("tool_id", "")),
                                    "arguments": action.get("arguments", {})}}

    def approval(self, state: ResearchState) -> dict:
        action = state["external_action"]
        digest = hashlib.sha256(json.dumps(action, sort_keys=True).encode()).hexdigest()
        approval_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{state['run_id']}:{digest}"))
        approval = self.db.query(WorkflowApproval).filter(WorkflowApproval.id == approval_id).first()
        if not approval:
            approval = WorkflowApproval(id=approval_id, run_id=state["run_id"], user_id=state["user_id"],
                tool_name=action["tool_id"], tool_type=action["tool_type"], arguments=redact_arguments(action["arguments"]),
                arguments_hash=digest, status="pending", expires_at=datetime.now(timezone.utc)+timedelta(days=1))
            self.db.add(approval); self.db.commit()
        decision = interrupt({"approval_id": approval.id, "tool_name": approval.tool_name,
                              "tool_type": approval.tool_type, "arguments": approval.arguments,
                              "arguments_hash": approval.arguments_hash})
        if decision.get("decision") == "reject":
            return {"approval": decision, "tool_result": {"rejected": True, "reason": decision.get("reason", "")}}
        result = self._execute_external(action, state)
        return {"approval": decision, "tool_result": result}

    def _execute_external(self, action: dict, state: ResearchState) -> dict:
        if action["tool_type"] == "connector":
            row = self.db.query(Connector).filter(Connector.id == action["tool_id"], Connector.user_id == state["user_id"]).first()
            if not row: raise ValueError("Approved connector is unavailable")
            secret = resolve_secret(self.db, state["user_id"], row.auth_secret_ref) if row.auth_secret_ref else None
            args = {**action["arguments"], "idempotency_key": state["run_id"]}
            return execute_connector(row.base_url, row.request_template, args, secret)
        row = (self.db.query(McpTool).join(McpServer)
               .filter(McpTool.id == action["tool_id"], McpServer.user_id == state["user_id"]).first())
        if not row: raise ValueError("Approved MCP tool is unavailable")
        import asyncio
        return asyncio.run(call_mcp_tool(row.mcp_server.url, row.tool_name, action["arguments"]))

    def draft(self, state: ResearchState) -> dict:
        run = self.db.query(Run).filter(Run.id == state["run_id"], Run.user_id == state["user_id"]).one()
        version = self._version(state)
        safe_version = copy.copy(version)
        safe_version.connector_allowlist = []
        safe_version.mcp_tool_allowlist = []
        if state.get("tool_result"):
            safe_version.skill = SimpleNamespace(
                system_prompt=version.skill.system_prompt,
                user_prompt_template=version.skill.user_prompt_template +
                "\n\nApproved workflow tool result: " + json.dumps(state["tool_result"])[:4000])
        import asyncio
        asyncio.run(execute_run(self.db, run, safe_version, version.agent_id, state["user_id"]))
        if run.status != "completed":
            raise RuntimeError((run.output or {}).get("error", "Workflow draft failed"))
        return {}

    def verify(self, state: ResearchState) -> dict:
        run = self.db.query(Run).filter(Run.id == state["run_id"]).one()
        errors = []
        if run.output is None: errors.append("missing_output")
        if state.get("evidence") and run.grounding_status == "grounded" and not run.citations:
            errors.append("missing_citations")
        return {"validation_errors": errors}

    @staticmethod
    def _after_verify(state: ResearchState) -> str:
        return "repair" if state.get("validation_errors") and state.get("repair_count", 0) < 1 else "finalize"

    @staticmethod
    def repair(state: ResearchState) -> dict:
        return {"repair_count": state.get("repair_count", 0) + 1}

    def finalize(self, state: ResearchState) -> dict:
        return {"completed": True}

    def _version(self, state: ResearchState):
        return self.db.query(AgentVersion).filter(AgentVersion.id == state["version_id"],
                                                  AgentVersion.user_id == state["user_id"]).one()
