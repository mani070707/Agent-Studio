import uuid

import httpx


class GeminiSession:
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
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt
        self.client = httpx.Client(timeout=timeout)
        self.contents: list[dict] = []
        self.provider = "gemini"
        self.usage = {"model_calls": 0, "input_tokens": 0, "output_tokens": 0}
        self.tools = [{"functionDeclarations": [{
            "name": tool["name"], "description": tool["description"], "parameters": tool["input_schema"]
        } for tool in tools]}]

    def _call(self) -> dict:
        response = self.client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            params={"key": self.api_key},
            json={
                "systemInstruction": {"parts": [{"text": self.system_prompt}]},
                "contents": self.contents,
                "tools": self.tools,
                "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
                "generationConfig": {"temperature": self.temperature, "maxOutputTokens": self.max_tokens},
            },
        )
        response.raise_for_status()
        payload = response.json()
        usage = payload.get("usageMetadata", {})
        self.usage["model_calls"] += 1
        self.usage["input_tokens"] += usage.get("promptTokenCount", 0)
        self.usage["output_tokens"] += usage.get("candidatesTokenCount", 0)
        parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        self.contents.append({"role": "model", "parts": parts})
        calls = []
        text = ""
        for part in parts:
            if "functionCall" in part:
                call = part["functionCall"]
                calls.append({"id": str(uuid.uuid4()), "name": call["name"], "arguments": call.get("args", {})})
            elif "text" in part:
                text += part["text"]
        return {"tool_calls": calls, "text": text}

    def send(self, user_message: str) -> dict:
        self.contents.append({"role": "user", "parts": [{"text": user_message}]})
        return self._call()

    def send_tool_results(self, results: list[dict]) -> dict:
        self.contents.append({"role": "user", "parts": [{"functionResponse": {
            "name": result["name"], "response": {"result": result["output"]}
        }} for result in results]})
        return self._call()
