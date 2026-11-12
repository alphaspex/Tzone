"""Local tool registry. Input: tool name + JSON arguments. Output: JSON-serializable result."""
import json
import math
from datetime import datetime, timezone
from collections import OrderedDict

_memory = OrderedDict()
MAX_SESSIONS = 64
MAX_MEMORY_KEYS = 32

def definitions():
    return [
      {"type":"function","function":{"name":"calculator","description":"Evaluate basic arithmetic using numbers, + - * / // % ** and parentheses.","parameters":{"type":"object","properties":{"expression":{"type":"string"}},"required":["expression"],"additionalProperties":False}}},
      {"type":"function","function":{"name":"get_current_time","description":"Get current UTC time in ISO-8601 format.","parameters":{"type":"object","properties":{},"additionalProperties":False}}},
      {"type":"function","function":{"name":"validate_json","description":"Check whether a string contains valid JSON.","parameters":{"type":"object","properties":{"text":{"type":"string"}},"required":["text"],"additionalProperties":False}}},
      {"type":"function","function":{"name":"memory_set","description":"Store a short note in this session's temporary memory.","parameters":{"type":"object","properties":{"key":{"type":"string"},"value":{"type":"string"}},"required":["key","value"],"additionalProperties":False}}},
      {"type":"function","function":{"name":"memory_get","description":"Read a note from this session's temporary memory.","parameters":{"type":"object","properties":{"key":{"type":"string"}},"required":["key"],"additionalProperties":False}}}
    ]

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
            return {"valid": False, "error": str(exc)}
    bucket = _memory.setdefault(session_id, {})
    _memory.move_to_end(session_id)
    while len(_memory) > MAX_SESSIONS:
        _memory.popitem(last=False)
    if name == "memory_set":
        key = str(arguments["key"])[:80]
        if key not in bucket and len(bucket) >= MAX_MEMORY_KEYS:
            return {"stored": False, "error": "Session memory limit reached"}
        bucket[key] = str(arguments["value"])[:2000]
        return {"stored": True}
    if name == "memory_get":
        return {"value": bucket.get(str(arguments["key"])[:80])}
    raise KeyError(name)
