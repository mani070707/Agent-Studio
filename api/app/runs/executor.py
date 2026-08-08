import re
from datetime import datetime, timezone

import jsonschema
from sqlalchemy.orm import Session

from app.connectors.executor import execute_connector
from app.core.secret_resolver import SecretResolutionError, resolve_provider_key, resolve_secret
from app.db.models import Connector, ContentItem, McpTool, Run, RunStep, Skill
from app.llm.factory import create_session
from app.mcp_client.client import call_tool as call_mcp_tool
from app.tools.registry import PLATFORM_TOOLS
from app.runs.free_policy import (
    FREE_LIMITS,
    BudgetExceeded,
    BudgetTracker,
    build_preflight,
    classify_provider_failure,
    failure_output,
)

MAX_ITERATIONS = 15
MAX_VALIDATION_RETRIES = 1
FINAL_ANSWER_TOOL = "final_answer"

_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


class RunFailedError(Exception):
    def __init__(self, code: str, reason: str, recommendations: list[str]):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.recommendations = recommendations


def _render_template(template: str, variables: dict) -> str:
    return _VAR_PATTERN.sub(lambda m: str(variables.get(m.group(1), "")), template)


def _extract_template_vars(template_obj) -> list[str]:
    return sorted({v for v in _VAR_PATTERN.findall(str(template_obj)) if v != "secret"})


def _build_tools_and_dispatch(db: Session, user_id: str, version, agent_id: str, output_json_schema: dict):
    """Assembles the LLM-facing tool list and a name -> async dispatch callable map from the
    version's allowlists. Every tool the model can call is enumerated here — the executor
    refuses to call anything not in this map."""
    tools = []
    dispatch = {}

    context = {"db": db, "agent_id": agent_id, "user_id": user_id}
    for name in version.tool_allowlist:
        module = PLATFORM_TOOLS.get(name)
        if not module:
            continue
        tools.append({"name": name, "description": module.DESCRIPTION, "input_schema": module.INPUT_SCHEMA})

        async def _platform_call(args, m=module, c=context):
            return m.run(args, c)

        dispatch[name] = ("tool_call", _platform_call)

    for mcp_tool_id in version.mcp_tool_allowlist:
        row = db.query(McpTool).filter(McpTool.id == mcp_tool_id).first()
        if not row:
            continue
        server = row.mcp_server
        tools.append(
            {"name": row.tool_name, "description": f"(via MCP server '{server.name}')", "input_schema": row.input_schema}
        )

        async def _mcp_call(args, url=server.url, tool_name=row.tool_name):
            return await call_mcp_tool(url, tool_name, args)

        dispatch[row.tool_name] = ("mcp_tool_call", _mcp_call)

    for connector_id in version.connector_allowlist:
        connector = db.query(Connector).filter(Connector.id == connector_id).first()
        if not connector:
            continue
        var_names = _extract_template_vars(connector.request_template)
        tool_name = f"connector_{connector.name}".replace(" ", "_")
        tools.append(
            {
                "name": tool_name,
                "description": f"Calls the '{connector.name}' connector.",
                "input_schema": {
                    "type": "object",
                    "properties": {v: {"type": "string"} for v in var_names},
                },
            }
        )
        secret_value = None
        if connector.auth_secret_ref:
            try:
                secret_value = resolve_secret(db, user_id, connector.auth_secret_ref)
            except SecretResolutionError:
                secret_value = None

        async def _connector_call(args, c=connector, sv=secret_value):
            return execute_connector(c.base_url, c.request_template, args, sv)

        dispatch[tool_name] = ("connector_call", _connector_call)

    for skill_id in version.skill_allowlist:
        skill = db.query(Skill).filter(Skill.id == skill_id).first()
        if not skill:
            continue
        tool_name = f"consult_skill_{skill.name}".replace(" ", "_")
        tools.append(
            {
                "name": tool_name,
                "description": f"Returns reference guidance from the '{skill.name}' skill for a question.",
                "input_schema": {"type": "object", "properties": {"question": {"type": "string"}}},
            }
        )

        async def _skill_call(args, s=skill):
            return {"skill_name": s.name, "guidance": s.system_prompt}

        dispatch[tool_name] = ("skill_consult", _skill_call)

    tools.append(
        {
            "name": FINAL_ANSWER_TOOL,
            "description": "Call this exactly once, when you have completed the task, with your final "
            "answer matching the required output schema.",
            "input_schema": output_json_schema,
        }
    )
    return tools, dispatch


def _log_step(db: Session, run_id: str, step_num: int, step_type: str, detail: dict) -> int:
    db.add(RunStep(run_id=run_id, step_num=step_num, type=step_type, detail=detail))
    db.commit()
    return step_num + 1


def build_run_prompts(version, run_input: dict) -> tuple[str, str]:
    guardrails = version.harness_config.get("prompt_guardrails", {})
    system_prompt = version.skill.system_prompt
    if guardrails.get("role"):
        system_prompt += f"\n\nRole: {guardrails['role']}"
    if guardrails.get("goal"):
        system_prompt += f"\nGoal: {guardrails['goal']}"
    system_prompt += (
        f"\n\nYou may only call the tools you have been given. When finished, call the "
        f"'{FINAL_ANSWER_TOOL}' tool exactly once with your final answer."
    )
    return system_prompt, _render_template(version.skill.user_prompt_template, run_input or {})


def preflight_for_run(db: Session, version, agent_id: str, run_input: dict) -> dict:
    system_prompt, user_prompt = build_run_prompts(version, run_input)
    selected_tools = (len(version.tool_allowlist) + len(version.mcp_tool_allowlist)
                      + len(version.connector_allowlist) + len(version.skill_allowlist))
    document_count = db.query(ContentItem).filter(ContentItem.agent_id == agent_id).count()
    return build_preflight(version.harness_config["runtime_model"], system_prompt, user_prompt,
                           run_input or {}, selected_tools, document_count)


async def execute_run(db: Session, run: Run, version, agent_id: str, user_id: str) -> None:
    """Runs the full agent loop for one `run` row, mutating it in place (status/output/timestamps)
    and appending `run_step` rows as it goes. Raises nothing — failures are recorded on the run."""
    run.status = "running"
    run.started_at = datetime.now(timezone.utc).isoformat()
    db.commit()
    step_num = 0

    runtime_model = version.harness_config["runtime_model"]
    free = runtime_model.get("usage_tier", "standard") == "free"
    budget = BudgetTracker(free=free)
    session = None
    last_text = ""
    completed_tools = []
    try:
        api_key = resolve_provider_key(db, user_id, runtime_model)
        tools, dispatch = _build_tools_and_dispatch(db, user_id, version, agent_id, version.output_schema.json_schema)
        system_prompt, user_message = build_run_prompts(version, run.input or {})
        preflight = preflight_for_run(db, version, agent_id, run.input or {})
        step_num = _log_step(db, run.id, step_num, "run_preflight", preflight)
        if free and preflight["estimated_input_tokens"] > FREE_LIMITS["input_tokens"]:
            raise BudgetExceeded("FREE_INPUT_TOKEN_BUDGET", "The rendered prompts exceed the free input-token budget.")
        session = create_session(
            provider=runtime_model["provider"], api_key=api_key, model=runtime_model["model_id"],
            temperature=runtime_model.get("temperature", 0),
            max_tokens=min(runtime_model.get("max_tokens", 4096), FREE_LIMITS["output_tokens_per_call"])
            if free else runtime_model.get("max_tokens", 4096),
            system_prompt=system_prompt, tools=tools,
            timeout=min(runtime_model.get("timeout_ms", 300000) / 1000, 90 if free else 300),
        )
        step_num = _log_step(db, run.id, step_num, "llm_call_started", {"message": user_message})
        budget.before_model_call()
        turn = session.send(user_message)
        validation_retries = 0
        no_tool_call_retries = 0

        while True:
            budget.before_iteration()
            last_text = turn["text"] or last_text
            step_num = _log_step(db, run.id, step_num, "llm_call_completed", {"tool_calls": turn["tool_calls"], "text": turn["text"]})

            if not turn["tool_calls"]:
                if no_tool_call_retries >= MAX_VALIDATION_RETRIES:
                    raise RunFailedError("MODEL_DID_NOT_CALL_TOOL",
                                         "The model did not call final_answer after a correction.", [
                                             "Choose a model with reliable tool-calling support.",
                                             "Simplify the system and user prompts."
                                         ])
                no_tool_call_retries += 1
                budget.before_model_call()
                turn = session.send(
                    f"You must call the '{FINAL_ANSWER_TOOL}' tool with your answer — do not reply with plain text."
                )
                continue

            final_call = next((tc for tc in turn["tool_calls"] if tc["name"] == FINAL_ANSWER_TOOL), None)
            if final_call:
                try:
                    jsonschema.validate(final_call["arguments"], version.output_schema.json_schema)
                except jsonschema.ValidationError as exc:
                    step_num = _log_step(db, run.id, step_num, "validation_error", {"error": str(exc)})
                    if validation_retries >= MAX_VALIDATION_RETRIES:
                        raise RunFailedError("OUTPUT_SCHEMA_INVALID",
                                             "The model could not produce an answer matching the output schema.", [
                                                 "Simplify the output schema.", "Use a stronger structured-output model."
                                             ]) from exc
                    validation_retries += 1
                    budget.before_model_call()
                    turn = session.send_tool_results(
                        [{"id": final_call["id"], "name": FINAL_ANSWER_TOOL, "output": {"error": str(exc)}}]
                    )
                    continue

                run.output = final_call["arguments"]
                run.status = "completed"
                run.completed_at = datetime.now(timezone.utc).isoformat()
                db.commit()
                return

            results = []
            for call in turn["tool_calls"]:
                if call["name"] not in dispatch:
                    results.append({"id": call["id"], "name": call["name"], "output": {"error": "Unknown tool"}})
                    continue
                step_type, fn = dispatch[call["name"]]
                budget.before_tool_call()
                step_num = _log_step(db, run.id, step_num, f"{step_type}_started", {"name": call["name"], "arguments": call["arguments"]})
                try:
                    output = await fn(call["arguments"])
                except Exception as exc:  # a tool failing shouldn't crash the run — feed the error back
                    output = {"error": str(exc)}
                step_num = _log_step(db, run.id, step_num, f"{step_type}_completed", {"name": call["name"], "output": output})
                completed_tools.append({"name": call["name"], "status": "failed" if isinstance(output, dict) and output.get("error") else "completed"})
                results.append({"id": call["id"], "name": call["name"], "output": output})

            budget.before_model_call()
            turn = session.send_tool_results(results)

    except SecretResolutionError as exc:
        code, reason, retryable, recommendations, retry_after = (
            "PROVIDER_CONNECTION_INVALID", str(exc), False,
            ["Select or test a provider connection in the agent harness."], None
        )
    except BudgetExceeded as exc:
        code, reason, retryable, recommendations, retry_after = exc.code, exc.reason, False, [
            "Reduce the prompt or enabled tools.", "Split the request into smaller tasks.",
            "Use a standard-tier key for extensive work."
        ], None
    except RunFailedError as exc:
        code, reason, retryable, recommendations, retry_after = exc.code, exc.reason, False, exc.recommendations, None
    except Exception as exc:
        code, reason, retryable, recommendations, retry_after = classify_provider_failure(exc)

    run.status = "failed"
    limits = FREE_LIMITS if free else {"iterations": MAX_ITERATIONS}
    run.output = failure_output(code, reason, budget.consumed(session), limits, recommendations,
                                retryable, retry_after, last_text, completed_tools)
    run.completed_at = datetime.now(timezone.utc).isoformat()
    _log_step(db, run.id, step_num, "run_failure_classified", run.output["failure"])
    db.commit()
