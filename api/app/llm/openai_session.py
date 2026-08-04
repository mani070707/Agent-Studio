import json

import openai


class OpenAISession:
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
        self.client = openai.OpenAI(api_key=api_key, timeout=timeout)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]
        self.messages: list[dict] = [{"role": "system", "content": system_prompt}]

    def _call(self) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.messages,
            tools=self.tools,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        choice = response.choices[0].message
        self.messages.append(choice.model_dump(exclude_none=True))
        tool_calls = [
            {"id": tc.id, "name": tc.function.name, "arguments": json.loads(tc.function.arguments)}
            for tc in (choice.tool_calls or [])
        ]
        return {"tool_calls": tool_calls, "text": choice.content or ""}

    def send(self, user_message: str) -> dict:
        self.messages.append({"role": "user", "content": user_message})
        return self._call()

    def send_tool_results(self, results: list[dict]) -> dict:
        for r in results:
            self.messages.append({"role": "tool", "tool_call_id": r["id"], "content": json.dumps(r["output"])})
        return self._call()
