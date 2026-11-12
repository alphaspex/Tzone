import unittest

from app import test_library, evaluator, tools, playground
from app.main import app


class CatalogTests(unittest.TestCase):
    def test_catalog_has_expected_size(self):
        self.assertEqual(test_library.count(), 165)
        self.assertEqual(len(test_library.category_summary()), 11)

    def test_public_case_does_not_expose_scoring(self):
        case = test_library.get_case("builtin-reasoning-foundation-01")
        public = test_library.public_case(case)
        self.assertNotIn("expected_output", public)
        self.assertNotIn("assertions", public)
        self.assertNotIn("judge_rubric", public)

    def test_difficulty_levels_are_complete(self):
        self.assertEqual(len(test_library.LEVELS), 5)
        for category in test_library.CATEGORIES:
            self.assertEqual(len(test_library.list_cases(category)), 15)


class EvaluatorTests(unittest.TestCase):
    def test_json_assertions(self):
        result = evaluator.run_assertions(
            '{"name":"Ada","age":37,"active":true}',
            [{"type":"json_valid"},{"type":"json_keys","values":["name","age","active"]}],
            [],
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["passed_count"], 2)

    def test_tool_call_assertion(self):
        result = evaluator.run_assertions(
            "19",
            [{"type":"tool_called","name":"calculator"}],
            [{"tool_name":"calculator","status":"ok"}],
        )
        self.assertTrue(result["passed"])

    def test_empty_assertions_are_skipped(self):
        result = evaluator.run_assertions("ok", [], [])
        self.assertTrue(result["passed"])
        self.assertTrue(result["skipped"])


class ToolTests(unittest.TestCase):
    def test_intent_tool_selection(self):
        self.assertIn("calculator", tools.select_for_task("Calculate 9 * 8"))
        self.assertIn("get_current_time", tools.select_for_task("What is the current UTC time?"))
        self.assertIn("validate_json", tools.select_for_task("Validate this JSON object"))

    def test_tool_definitions_are_filtered(self):
        definitions = tools.definitions(["calculator"])
        self.assertEqual([x["function"]["name"] for x in definitions], ["calculator"])

    def test_parameter_allowlist(self):
        result = playground.normalize_parameters({"temperature":0.2,"tools":[{"name":"bad"}],"max_tokens":50})
        self.assertEqual(result, {"temperature":0.2,"max_tokens":50})


class ApiTests(unittest.TestCase):
    def test_ui_routes_are_registered(self):
        paths = {route.path for route in app.routes}
        self.assertIn("/ui/dashboard", paths)
        self.assertIn("/ui/agent/chat", paths)
        self.assertIn("/ui/runs/{run_id}/stream", paths)
        self.assertIn("/v1/chat/completions", paths)


if __name__ == "__main__":
    unittest.main()
