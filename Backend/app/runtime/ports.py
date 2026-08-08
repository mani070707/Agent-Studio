from typing import Protocol


class RuntimeSessionPort(Protocol):
    provider: str
    usage: dict

    def send(self, user_message: str) -> dict: ...

    def send_tool_results(self, results: list[dict]) -> dict: ...

    def stats(self) -> dict: ...
