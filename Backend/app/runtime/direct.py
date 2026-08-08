from time import monotonic


class DirectRuntimeSession:
    """Normalizes the existing provider sessions behind the application runtime port."""

    def __init__(self, session) -> None:
        self.session = session
        self.provider = session.provider
        self.usage = session.usage
        self._latency_ms = 0.0

    def _timed(self, operation, *args):
        started = monotonic()
        try:
            return operation(*args)
        finally:
            self._latency_ms += (monotonic() - started) * 1000

    def send(self, user_message: str) -> dict:
        return self._timed(self.session.send, user_message)

    def send_tool_results(self, results: list[dict]) -> dict:
        return self._timed(self.session.send_tool_results, results)

    def stats(self) -> dict:
        return {**self.usage, "provider_latency_ms": round(self._latency_ms, 2),
                "orchestration_overhead_ms": 0.0}
