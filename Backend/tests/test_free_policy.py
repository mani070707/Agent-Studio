import unittest

from app.runs.free_policy import (
    BudgetExceeded,
    BudgetTracker,
    FREE_LIMITS,
    build_preflight,
    classify_provider_failure,
    failure_output,
)


class FreePolicyTest(unittest.TestCase):
    def test_preflight_detects_large_multi_task_request(self):
        prompt = "\n".join(f"{number}. complete task {number}" for number in range(1, 7))
        result = build_preflight(
            {"usage_tier": "free"}, "system", prompt, {}, selected_tools=5, document_count=4
        )
        self.assertTrue(result["high_complexity"])
        self.assertEqual(result["likely_subtasks"], 6)
        self.assertGreaterEqual(len(result["warnings"]), 3)

    def test_free_model_call_budget_stops_before_extra_call(self):
        budget = BudgetTracker(free=True)
        for _ in range(FREE_LIMITS["model_calls"]):
            budget.before_model_call()
        with self.assertRaises(BudgetExceeded) as error:
            budget.before_model_call()
        self.assertEqual(error.exception.code, "FREE_MODEL_CALL_BUDGET")
        self.assertEqual(budget.model_calls, FREE_LIMITS["model_calls"])

    def test_rate_limit_is_retryable_without_exposing_provider_body(self):
        class Response:
            status_code = 429
            headers = {"retry-after": "30"}

        class ProviderException(Exception):
            response = Response()

        code, reason, retryable, _, retry_after = classify_provider_failure(ProviderException("secret body"))
        self.assertEqual(code, "FREE_QUOTA_EXHAUSTED")
        self.assertTrue(retryable)
        self.assertEqual(retry_after, "30")
        self.assertNotIn("secret body", reason)

    def test_failure_output_preserves_compatibility_and_safe_progress(self):
        output = failure_output(
            "FREE_TOOL_CALL_BUDGET", "Tool budget exhausted", {"tool_calls": 3}, FREE_LIMITS,
            ["Split the task"], partial_text="Completed the first item",
            completed_tools=[{"name": "calculator", "status": "completed"}],
        )
        self.assertEqual(output["error"], "Tool budget exhausted")
        self.assertEqual(output["failure"]["code"], "FREE_TOOL_CALL_BUDGET")
        self.assertEqual(output["partial_output"]["completed_tools"][0]["name"], "calculator")


if __name__ == "__main__":
    unittest.main()
