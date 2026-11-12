"""Meta model catalogue. Pure data: model ids, request capabilities, prices and defaults."""
from copy import deepcopy

MODELS = [
    {
        "id": "muse-wonder-1.0", "name": "Muse Wonder 1.0", "family": "Wonder",
        "mode": "Standard", "contributor": False,
        "input_per_million": 4.00, "output_per_million": 20.00,
        "cached_input_per_million": 0.20, "context_window": 1048576,
        "default_reasoning_effort": "max", "max_reasoning_effort": True,
        "description": "Highest-capability model for complex engineering and long-horizon agent work."
    },
    {
        "id": "muse-spark-1.3", "name": "Muse Spark 1.3", "family": "Spark",
        "mode": "Standard", "contributor": False,
        "input_per_million": 1.25, "output_per_million": 4.25,
        "cached_input_per_million": 0.15, "context_window": 1048576,
        "default_reasoning_effort": "high", "max_reasoning_effort": True,
        "description": "Recommended general-purpose model for agentic and coding workloads."
    },
    {
        "id": "muse-spark-1.2", "name": "Muse Spark 1.2", "family": "Spark",
        "mode": "Standard", "contributor": False,
        "input_per_million": 1.25, "output_per_million": 4.25,
        "cached_input_per_million": 0.15, "context_window": 1048576,
        "default_reasoning_effort": "high", "max_reasoning_effort": False,
        "description": "Previous Muse Spark generation; useful for version comparisons."
    },
    {
        "id": "muse-spark-1.1", "name": "Muse Spark 1.1", "family": "Spark",
        "mode": "Standard", "contributor": False,
        "input_per_million": 1.25, "output_per_million": 4.25,
        "cached_input_per_million": 0.15, "context_window": 1048576,
        "default_reasoning_effort": "high", "max_reasoning_effort": False,
        "description": "Earlier Muse Spark version; useful for regression comparisons."
    },
    {
        "id": "muse-spark-1.3-contributor", "name": "Muse Spark 1.3 Contributor", "family": "Spark",
        "mode": "Contributor", "contributor": True,
        "input_per_million": 0.10, "output_per_million": 0.20,
        "cached_input_per_million": 0.002, "context_window": 1048576,
        "default_reasoning_effort": "high", "max_reasoning_effort": False,
        "description": "Discounted Contributor mode. Meta may use submitted content to train future models."
    },
    {
        "id": "muse-spark-1.2-contributor", "name": "Muse Spark 1.2 Contributor", "family": "Spark",
        "mode": "Contributor", "contributor": True,
        "input_per_million": 0.10, "output_per_million": 0.20,
        "cached_input_per_million": 0.002, "context_window": 1048576,
        "default_reasoning_effort": "high", "max_reasoning_effort": False,
        "description": "Discounted Contributor mode. Meta may use submitted content to train future models."
    },
    {
        "id": "muse-ember-1.0", "name": "Muse Ember 1.0", "family": "Ember",
        "mode": "Standard", "contributor": False,
        "input_per_million": 0.10, "output_per_million": 0.50,
        "cached_input_per_million": 0.004, "context_window": 1048576,
        "long_context_threshold": 200000,
        "long_context_input_per_million": 0.30,
        "long_context_output_per_million": 1.50,
        "long_context_cached_input_per_million": 0.012,
        "default_reasoning_effort": "max", "max_reasoning_effort": True,
        "description": "Efficient execution for high-volume tool calls and bounded subtasks."
    },
]

_BASE_EFFORTS = ["minimal", "low", "medium", "high", "xhigh", "max"]


def get_model(model_id):
    for model in MODELS:
        if model["id"] == model_id:
            return deepcopy(model)
    return None


def list_models():
    return deepcopy(MODELS)


def reasoning_efforts(model_id):
    model = get_model(model_id)
    if not model:
        return []
    return [value for value in _BASE_EFFORTS
            if value != "max" or model["max_reasoning_effort"]]


def validate_reasoning_effort(model_id, effort):
    if effort in (None, "", "auto"):
        return None
    if effort not in reasoning_efforts(model_id):
        allowed = ", ".join(reasoning_efforts(model_id))
        raise ValueError(f"Reasoning effort '{effort}' is not supported by {model_id}. Choose: {allowed}")
    return effort


def public_models():
    result = []
    for model in MODELS:
        item = deepcopy(model)
        item["reasoning_efforts"] = reasoning_efforts(model["id"])
        result.append(item)
    return result


def estimate_price(model_id, input_tokens=0, output_tokens=0, cached_input_tokens=0):
    model = get_model(model_id)
    if not model:
        return None
    ordinary_input = max(0, int(input_tokens) - max(0, int(cached_input_tokens)))
    cached = max(0, int(cached_input_tokens))
    if (model_id == "muse-ember-1.0" and int(input_tokens) > model["long_context_threshold"]):
        in_rate = model["long_context_input_per_million"]
        cached_rate = model["long_context_cached_input_per_million"]
        out_rate = model["long_context_output_per_million"]
    else:
        in_rate = model["input_per_million"]
        cached_rate = model["cached_input_per_million"]
        out_rate = model["output_per_million"]
    return round((ordinary_input * in_rate + cached * cached_rate
                  + max(0, int(output_tokens)) * out_rate) / 1_000_000, 8)
