"""Local tool registry. Inputs: tool name and JSON arguments. Output: bounded JSON-serializable result."""
import json
import math
import re
from datetime import datetime, timezone
from collections import OrderedDict

_memory = OrderedDict()
MAX_SESSIONS = 64
MAX_MEMORY_KEYS = 32

_TOOL_DEFS = [
    {"type":"function","function":{"name":"calculator","description":"Evaluate arithmetic expressions using numbers, + - * / // % ** and parentheses.","parameters":{"type":"object","properties":{"expression":{"type":"string"}},"required":["expression"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"get_current_time","description":"Get the current UTC time in ISO-8601 format.","parameters":{"type":"object","properties":{},"additionalProperties":False}}},
    {"type":"function","function":{"name":"validate_json","description":"Check whether a string contains valid JSON and return the parsed value when valid.","parameters":{"type":"object","properties":{"text":{"type":"string"}},"required":["text"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"memory_set","description":"Store a short note in this conversation's temporary memory for later retrieval.","parameters":{"type":"object","properties":{"key":{"type":"string"},"value":{"type":"string"}},"required":["key","value"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"memory_get","description":"Retrieve a note previously stored in this conversation's temporary memory.","parameters":{"type":"object","properties":{"key":{"type":"string"}},"required":["key"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"convert_units","description":"Convert common length, mass, and temperature units.","parameters":{"type":"object","properties":{"value":{"type":"number"},"from_unit":{"type":"string"},"to_unit":{"type":"string"}},"required":["value","from_unit","to_unit"],"additionalProperties":False}}},
]

def available_names():
    return [item["function"]["name"] for item in _TOOL_DEFS]

def definitions(names=None):
    """Return normal tool definitions, optionally filtered to a scenario-selected set."""
    if names is None:
        return list(_TOOL_DEFS)
    wanted = set(names)
    return [item for item in _TOOL_DEFS if item["function"]["name"] in wanted]

def select_for_task(text):
    """Select ordinary tools from task intent. No evaluation metadata is consulted."""
    value = (text or "").lower()
    selected = []
    math_words = r"\b(calculate|compute|multiply|divide|sum|product|average|percentage|percent|how many|how much|rate|convert)\b"
    if re.search(math_words, value) or re.search(r"\d\s*[*/+%-]\s*\d", value):
        selected.append("calculator")
    if any(term in value for term in ("current time", "utc", "what time", "today's date", "current date")):
        selected.append("get_current_time")
    if "json" in value or "schema" in value or "validate" in value:
        selected.append("validate_json")
    if any(term in value for term in ("remember", "recall", "store this", "keep in mind", "save this note")):
        selected.extend(["memory_set", "memory_get"])
    if "convert" in value and any(unit in value for unit in ("kilomet", "mile", "meter", "feet", "pound", "kilogram", "celsius", "fahrenheit")):
        selected.append("convert_units")
    # For an open-ended conversation, expose only low-risk tools likely to be useful.
    return list(dict.fromkeys(selected))

def _safe_math(expression):
    import ast
    if len(expression) > 200:
        raise ValueError("Expression too long")
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd)
    tree = ast.parse(expression, mode="eval")
    nodes = list(ast.walk(tree))
    if any(not isinstance(node, allowed) for node in nodes) or len(nodes) > 40:
        raise ValueError("Unsupported or overly complex expression")
    for node in nodes:
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            if not isinstance(node.right, ast.Constant) or not isinstance(node.right.value, (int, float)) or abs(node.right.value) > 100:
                raise ValueError("Exponent out of range")
    value = eval(compile(tree, "<calculator>", "eval"), {"__builtins__": {}}, {})
    if not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1e100:
        raise ValueError("Result is outside the supported range")
    return value

def _convert(value, source, target):
    aliases = {"km":"kilometer","kilometers":"kilometer","m":"meter","meters":"meter","mi":"mile","miles":"mile","ft":"foot","feet":"foot","kg":"kilogram","g":"gram","lb":"pound","lbs":"pound"}
    source, target = aliases.get(source.lower(), source.lower()), aliases.get(target.lower(), target.lower())
    length = {"meter":1.0,"kilometer":1000.0,"mile":1609.344,"foot":0.3048}
    mass = {"gram":1.0,"kilogram":1000.0,"pound":453.59237}
    if source in length and target in length:
        return value * length[source] / length[target]
    if source in mass and target in mass:
        return value * mass[source] / mass[target]
    if source == "celsius" and target == "fahrenheit":
        return value * 9 / 5 + 32
    if source == "fahrenheit" and target == "celsius":
        return (value - 32) * 5 / 9
    if source == target:
        return value
    raise ValueError("Unsupported or incompatible units")

def run(name, arguments, session_id):
    if name == "calculator":
        return {"result": _safe_math(str(arguments["expression"]))}
    if name == "get_current_time":
        return {"utc": datetime.now(timezone.utc).isoformat()}
    if name == "validate_json":
        try:
            parsed = json.loads(arguments["text"])
            return {"valid": True, "data": parsed}
        except Exception as exc:
            return {"valid": False, "error": str(exc)[:300]}
    if name == "convert_units":
        return {"value": _convert(float(arguments["value"]), str(arguments["from_unit"]), str(arguments["to_unit"]))}
    if name in ("memory_set", "memory_get"):
        bucket = _memory.setdefault(session_id, {})
        _memory.move_to_end(session_id)
        while len(_memory) > MAX_SESSIONS:
            _memory.popitem(last=False)
        if name == "memory_set":
            key = str(arguments["key"])[:80]
            if key not in bucket and len(bucket) >= MAX_MEMORY_KEYS:
                return {"stored":False,"error":"Session memory limit reached"}
            bucket[key] = str(arguments["value"])[:2000]
            return {"stored":True}
        return {"value":bucket.get(str(arguments["key"])[:80])}
    raise KeyError(name)
