import unittest

from app import test_library, evaluator, tools, playground, model_catalog
from app.main import app
from app import ui_store


class CatalogTests(unittest.TestCase):
    def test_catalog_has_expected_size(self):
        self.assertEqual(test_library.count(), 165)
        self.assertEqual(len(test_library.category_summary()), 11)

    def test_public_case_does_not_expose_scoring(self):
        case = test_library.get_case("meta-reasoning-easy-01")
        public = test_library.public_case(case)
        self.assertNotIn("expected_output", public)
        self.assertNotIn("assertions", public)
        self.assertNotIn("judge_rubric", public)

    def test_difficulty_levels_are_complete(self):
        self.assertEqual(test_library.LEVELS, ["easy", "mid", "hard", "expert", "adversarial"])
        for category in test_library.CATEGORIES:
            cases = test_library.list_cases(category)
            self.assertEqual(len(cases), 15)
            first_scenario = [
                test_library.get_case("meta-" + category + "-" + level + "-01")["user_prompt"]
                for level in test_library.LEVELS
            ]
            self.assertEqual(len(set(first_scenario)), 5)

    def test_public_difficulty_labels_are_named(self):
        case = test_library.get_case("meta-reasoning-adversarial-01")
        self.assertEqual(case["difficulty_label"], "Adversarial")
        self.assertIn("untrusted", case["user_prompt"].lower())


class EvaluatorTests(unittest.TestCase):
    def test_markdown_fenced_json(self):
        self.assertEqual(evaluator._json_value(chr(96) * 3 + "json
{\"ok\":true}
" + chr(96) * 3), {"ok": True})

    def test_json_assertions(self):
        result = evaluator.run_assertions(
            '{"name":"Ada","age":37,"active":true}',
            [{"type":"json_valid"}, {"type":"json_keys", "values":["name", "age", "active"]}],
            [],
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["passed_count"], 2)

    def test_tool_call_assertion(self):
        result = evaluator.run_assertions(
            "19",
            [{"type":"tool_called", "name":"calculator"}],
            [{"tool_name":"calculator", "status":"ok"}],
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

    def test_meta_responses_parameter_allowlist(self):
        result = playground.normalize_parameters(
            {"temperature": 0.2, "max_output_tokens": 50, "reasoning_effort": "high"},
            "muse-spark-1.3",
        )
        self.assertEqual(result, {
            "temperature": 0.2, "max_output_tokens": 50, "reasoning_effort": "high"
        })

    def test_chat_completions_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            playground.normalize_parameters({"max_tokens": 50}, "muse-spark-1.3")

    def test_model_catalog_efforts(self):
        self.assertIn("max", model_catalog.reasoning_efforts("muse-wonder-1.0"))
        self.assertNotIn("max", model_catalog.reasoning_efforts("muse-spark-1.2"))


class MemoryBoundTests(unittest.TestCase):
    def test_run_cache_is_bounded(self):
        ui_store._RUNS.clear()
        ui_store._EVENTS.clear()
        for index in range(45):
            ui_store._cache_run({"id": "run-" + str(index)})
        self.assertLessEqual(len(ui_store._RUNS), ui_store._MAX_MEMORY_RUNS)

    def test_custom_cache_is_bounded(self):
        ui_store._CUSTOM.clear()
        for index in range(220):
            ui_store._cache_custom({"id": "custom-" + str(index)})
        self.assertLessEqual(len(ui_store._CUSTOM), ui_store._MAX_CUSTOM)


class ApiTests(unittest.TestCase):
    def test_meta_responses_routes_are_registered(self):
        paths = {route.path for route in app.routes}
        self.assertIn("/ui/dashboard", paths)
        self.assertIn("/ui/agent/chat", paths)
        self.assertIn("/ui/runs/{run_id}/stream", paths)
        self.assertIn("/v1/responses", paths)
        self.assertIn("/v1/models", paths)
        self.assertNotIn("/v1/chat/completions", paths)


if __name__ == "__main__":
    unittest.main()
