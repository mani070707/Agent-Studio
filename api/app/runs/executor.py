import re
from datetime import datetime, timezone

import jsonschema
from sqlalchemy.orm import Session

from app.connectors.executor import execute_connector
from app.core.secret_resolver import SecretResolutionError, resolve_secret
from app.db.models import Connector, McpTool, Run, RunStep, Skill
from app.llm.factory import create_session
from app.mcp_client.client import call_tool as call_mcp_tool
from app.tools.registry import PLATFORM_TOOLS

MAX_ITERATIONS = 15
MAX_VALIDATION_RETRIES = 1
FINAL_ANSWER_TOOL = "final_answer"

_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


class RunFailedError(Exception):
    pass


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


async def execute_run(db: Session, run: Run, version, agent_id: str, user_id: str) -> None:
    """Runs the full agent loop for one `run` row, mutating it in place (status/output/timestamps)
    and appending `run_step` rows as it goes. Raises nothing — failures are recorded on the run."""
    run.status = "running"
    run.started_at = datetime.now(timezone.utc).isoformat()
    db.commit()
    step_num = 0

    try:
        runtime_model = version.harness_config["runtime_model"]
        api_key = resolve_secret(db, user_id, runtime_model["api_key_secret_ref"])
    except SecretResolutionError as exc:
        run.status = "failed"
        run.output = {"error": str(exc)}
        run.completed_at = datetime.now(timezone.utc).isoformat()
        db.commit()
        return

    tools, dispatch = _build_tools_and_dispatch(db, user_id, version, agent_id, version.output_schema.json_schema)

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
    user_message = _render_template(version.skill.user_prompt_template, run.input or {})

    session = create_session(
        provider=runtime_model["provider"],
        api_key=api_key,
        model=runtime_model["model_id"],
        temperature=runtime_model.get("temperature", 0),
        max_tokens=runtime_model.get("max_tokens", 4096),
        system_prompt=system_prompt,
        tools=tools,
    )

    try:
        step_num = _log_step(db, run.id, step_num, "llm_call_started", {"message": user_message})
        turn = session.send(user_message)
        validation_retries = 0
        no_tool_call_retries = 0

        for _ in range(MAX_ITERATIONS):
            step_num = _log_step(db, run.id, step_num, "llm_call_completed", {"tool_calls": turn["tool_calls"], "text": turn["text"]})

            if not turn["tool_calls"]:
                if no_tool_call_retries >= MAX_VALIDATION_RETRIES:
                    raise RunFailedError("Model did not call any tool, including final_answer, after a retry.")
                no_tool_call_retries += 1
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
                        raise RunFailedError(f"Final answer failed schema validation twice: {exc}") from exc
                    validation_retries += 1
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
                step_num = _log_step(db, run.id, step_num, f"{step_type}_started", {"name": call["name"], "arguments": call["arguments"]})
                try:
                    output = await fn(call["arguments"])
                except Exception as exc:  # a tool failing shouldn't crash the run — feed the error back
                    output = {"error": str(exc)}
                step_num = _log_step(db, run.id, step_num, f"{step_type}_completed", {"name": call["name"], "output": output})
                results.append({"id": call["id"], "name": call["name"], "output": output})

            turn = session.send_tool_results(results)

        raise RunFailedError(f"Exceeded {MAX_ITERATIONS} iterations without a final answer.")

    except RunFailedError as exc:
        run.status = "failed"
        run.output = {"error": str(exc)}
        run.completed_at = datetime.now(timezone.utc).isoformat()
        db.commit()
    except Exception as exc:  # LLM provider errors (bad key, rate limit, etc.)
        run.status = "failed"
        run.output = {"error": f"Run failed: {exc}"}
        run.completed_at = datetime.now(timezone.utc).isoformat()
        db.commit()
