import unittest

from app import evaluator, model_catalog, playground, test_library, tools


class MetaModelCatalogTests(unittest.TestCase):
    def test_seven_supported_models_have_pricing_and_efforts(self):
        models = model_catalog.list_models()
        self.assertEqual(len(models), 7)
        self.assertEqual(
            {item["id"] for item in models},
            {
                "muse-wonder-1.0",
                "muse-spark-1.3",
                "muse-spark-1.2",
                "muse-spark-1.1",
                "muse-spark-1.3-contributor",
                "muse-spark-1.2-contributor",
                "muse-ember-1.0",
            },
        )
        for item in models:
            self.assertGreater(item["input_per_million"], 0)
            self.assertGreater(item["output_per_million"], 0)
            self.assertIn("high", model_catalog.reasoning_efforts(item["id"]))

    def test_reasoning_effort_is_model_specific(self):
        self.assertIn("max", model_catalog.reasoning_efforts("muse-wonder-1.0"))
        self.assertIn("max", model_catalog.reasoning_efforts("muse-spark-1.3"))
        self.assertNotIn("max", model_catalog.reasoning_efforts("muse-spark-1.2"))
        self.assertNotIn("max", model_catalog.reasoning_efforts("muse-spark-1.3-contributor"))
        with self.assertRaises(ValueError):
            model_catalog.validate_reasoning_effort("muse-spark-1.2", "max")
        self.assertIsNone(model_catalog.validate_reasoning_effort("muse-spark-1.2", "auto"))

    def test_published_prices_are_used_for_estimates(self):
        cost = model_catalog.estimate_price(
            "muse-spark-1.3", input_tokens=1_000_000,
            output_tokens=1_000_000, cached_input_tokens=0,
        )
        self.assertEqual(cost, 5.5)
        ember = model_catalog.estimate_price(
            "muse-ember-1.0", input_tokens=200_001,
            output_tokens=100_000, cached_input_tokens=20_000,
        )
        expected = (180_001 * 0.30 + 20_000 * 0.012 + 100_000 * 1.50) / 1_000_000
        self.assertEqual(ember, round(expected, 8))


class MetaResponsesRequestTests(unittest.TestCase):
    def test_normalizer_accepts_meta_responses_parameters(self):
        params = playground.normalize_parameters(
            {"max_output_tokens": 4096, "reasoning_effort": "xhigh", "temperature": 0.2},
            "muse-spark-1.3",
        )
        self.assertEqual(params["max_output_tokens"], 4096)
        self.assertEqual(params["reasoning_effort"], "xhigh")
        self.assertEqual(params["temperature"], 0.2)
        self.assertNotIn("max_tokens", params)

    def test_normalizer_rejects_chat_completions_only_parameters(self):
        with self.assertRaises(ValueError):
            playground.normalize_parameters({"max_tokens": 512}, "muse-spark-1.3")
        with self.assertRaises(ValueError):
            playground.normalize_parameters({"presence_penalty": 0.1}, "muse-spark-1.3")
        with self.assertRaises(ValueError):
            playground.normalize_parameters({"temperature": 0.2, "top_p": 0.8}, "muse-spark-1.3")

    def test_output_token_minimum_is_enforced(self):
        params = playground.normalize_parameters({"max_output_tokens": 2}, "muse-spark-1.3")
        self.assertEqual(params["max_output_tokens"], 16)

    def test_local_function_tools_use_responses_shape(self):
        definitions = tools.responses_definitions(["calculator"])
        self.assertEqual(len(definitions), 1)
        self.assertEqual(definitions[0]["type"], "function")
        self.assertEqual(definitions[0]["name"], "calculator")
        self.assertIn("parameters", definitions[0])
        self.assertNotIn("function", definitions[0])


class MetaBenchmarkLibraryTests(unittest.TestCase):
    def test_new_suite_has_165_cases_and_five_named_levels(self):
        self.assertEqual(test_library.count(), 165)
        self.assertEqual(test_library.LEVELS, ["easy", "mid", "hard", "expert", "adversarial"])
        self.assertEqual(len(test_library.category_summary()), 11)
        for category in test_library.CATEGORIES:
            self.assertEqual(
                sum(1 for item in test_library.list_cases(category=category)),
                15,
            )
        for level in test_library.LEVELS:
            self.assertEqual(
                sum(1 for item in test_library.list_cases(difficulty=level)),
                33,
            )

    def test_each_difficulty_has_three_distinct_scenarios_per_category(self):
        for category in test_library.CATEGORIES:
            for level in test_library.LEVELS:
                cases = [
                    case for case in test_library.list_cases(category=category, difficulty=level)
                    if case["is_builtin"]
                ]
                self.assertEqual(len(cases), 3)
                self.assertTrue(all(case["difficulty_label"] == test_library.LEVEL_METADATA[level]["label"] for case in cases))

    def test_builtin_parameters_do_not_contain_legacy_chat_options(self):
        forbidden = {"max_tokens", "presence_penalty", "frequency_penalty", "stop", "logit_bias", "n"}
        for case in test_library._CASES.values():
            self.assertFalse(forbidden.intersection((case.get("parameters") or {}).keys()), case["id"])
            self.assertGreaterEqual((case.get("parameters") or {}).get("max_output_tokens", 16), 16)

    def test_adversarial_suite_preserves_required_output_format(self):
        exact = test_library.get_case("meta-latency_tokens-adversarial-02")
        self.assertIn("exactly this string", exact["user_prompt"])
        self.assertIn("output format", exact["user_prompt"])


class EvaluationTests(unittest.TestCase):
    def test_streaming_assertion_counts_text_delta_events(self):
        result = evaluator.run_assertions(
            "streamed text", [{"type": "stream_event_count_min", "value": 3}], [], stream_event_count=4
        )
        self.assertTrue(result["passed"])
        failed = evaluator.run_assertions(
            "streamed text", [{"type": "stream_event_count_min", "value": 3}], [], stream_event_count=1
        )
        self.assertFalse(failed["passed"])

    def test_json_path_assertion_supports_array_indices(self):
        result = evaluator.run_assertions(
            '{"items":[{"sku":"A-1"}]}',
            [{"type": "json_path_exists", "path": "items.0.sku"}],
            [],
        )
        self.assertTrue(result["passed"])

    def test_meta_usage_is_accumulated_without_chat_token_field_names(self):
        usage = {}
        playground._add_usage(usage, {
            "input_tokens": 100, "output_tokens": 40, "total_tokens": 140,
            "input_tokens_details": {"cached_tokens": 25},
            "output_tokens_details": {"reasoning_tokens": 12},
        })
        playground._add_usage(usage, {
            "input_tokens": 50, "output_tokens": 20, "total_tokens": 70,
            "input_tokens_details": {"cached_tokens": 5},
        })
        self.assertEqual(usage["input_tokens"], 150)
        self.assertEqual(usage["output_tokens"], 60)
        self.assertEqual(usage["total_tokens"], 210)
        self.assertEqual(usage["cached_input_tokens"], 30)
        self.assertEqual(usage["reasoning_tokens"], 12)


if __name__ == "__main__":
    unittest.main()
