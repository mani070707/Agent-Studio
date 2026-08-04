import json

import anthropic


class AnthropicSession:
    def __init__(
        self,
        api_key: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: str,
        tools: list[dict],
        timeout: float = 300.0,
    ):
        self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt
        self.tools = [
            {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
            for t in tools
        ]
        self.messages: list[dict] = []

    def _call(self) -> dict:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=self.system_prompt,
            messages=self.messages,
            tools=self.tools,
        )
        self.messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
        tool_calls = [
            {"id": block.id, "name": block.name, "arguments": block.input}
            for block in response.content
            if block.type == "tool_use"
        ]
        text = "".join(block.text for block in response.content if block.type == "text")
        return {"tool_calls": tool_calls, "text": text}

    def send(self, user_message: str) -> dict:
        self.messages.append({"role": "user", "content": user_message})
        return self._call()

    def send_tool_results(self, results: list[dict]) -> dict:
        content = [
            {"type": "tool_result", "tool_use_id": r["id"], "content": json.dumps(r["output"])}
            for r in results
        ]
        self.messages.append({"role": "user", "content": content})
        return self._call()
