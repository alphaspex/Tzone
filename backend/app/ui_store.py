"""UI persistence boundary. Inputs: typed records from UI services. Outputs: decoded records; bounded memory fallback when D1 is not configured."""
import json
from collections import deque
from . import store

_CUSTOM = {}
_RUNS = {}
_EVENTS = {}
_MESSAGES = {}
_METRICS = deque(maxlen=2000)
_TOOL_EVENTS = deque(maxlen=1000)
_AGENT_STATES = {}
_HARNESS_SETTINGS = {}
_MAX_AGENT_STATES = 32
_MAX_AGENT_STATE_CHARS = 4_000_000
_MAX_MEMORY_RUNS = 30
_MAX_MEMORY_CONVERSATIONS = 32
_MAX_CUSTOM = 200

def _cache_run(item):
    _RUNS[item["id"]] = item
    while len(_RUNS) > _MAX_MEMORY_RUNS:
        oldest_id = next(iter(_RUNS))
        _RUNS.pop(oldest_id, None)
        _EVENTS.pop(oldest_id, None)

def _cache_custom(item):
    _CUSTOM[item["id"]] = item
    while len(_CUSTOM) > _MAX_CUSTOM:
        _CUSTOM.pop(next(iter(_CUSTOM)), None)

def _json(value, default=None):
    if value is None:
        return default
    try:
        return json.loads(value) if isinstance(value, str) else value
    except Exception:
        return default

async def _rows(sql, params=None):
    raw = await store.execute(sql, params or [])
    if not raw:
        return []
    if isinstance(raw, dict):
        return raw.get("results") or []
    if isinstance(raw, list):
        rows = []
        for item in raw:
            if isinstance(item, dict) and isinstance(item.get("results"), list):
                rows.extend(item["results"])
        return rows
    return []

async def start_ui_store():
    statements = [
        "CREATE TABLE IF NOT EXISTS custom_tests (id TEXT PRIMARY KEY, category TEXT NOT NULL, difficulty TEXT, definition_json TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS run_events (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, event_type TEXT NOT NULL, event_json TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)",
        "CREATE INDEX IF NOT EXISTS idx_run_events_run_id ON run_events(run_id)",
        "CREATE INDEX IF NOT EXISTS idx_test_runs_created ON test_runs(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)",
    ]
    if store.configured():
        for sql in statements:
            await store.execute(sql)
    await reset_meta_workspace_once()

async def reset_meta_workspace_once():
    """Clear pre-Meta workspace data once; future deploys preserve newly created records."""
    _CUSTOM.clear()
    _RUNS.clear()
    _EVENTS.clear()
    _MESSAGES.clear()
    _METRICS.clear()
    _TOOL_EVENTS.clear()
    _AGENT_STATES.clear()
    _HARNESS_SETTINGS.clear()
    if not store.configured():
        return {"applied": False, "persistence": "memory"}
    marker = "meta_model_api_workspace_reset_v1"
    rows = await _rows("SELECT migration_id FROM workspace_migrations WHERE migration_id = ? LIMIT 1", [marker])
    if rows:
        return {"applied": False, "persistence": "d1"}
    for table in ("run_events", "custom_tests", "test_runs", "messages", "sessions", "tool_events", "metrics", "agent_states", "harness_settings"):
        await store.execute(f"DELETE FROM {table}")
    await store.execute("INSERT INTO workspace_migrations (migration_id) VALUES (?)", [marker])
    return {"applied": True, "persistence": "d1"}

async def get_harness_settings():
    if _HARNESS_SETTINGS:
        return dict(_HARNESS_SETTINGS)
    if not store.configured():
        return {}
    rows = await _rows("SELECT value_json FROM harness_settings WHERE setting_key = ? LIMIT 1", ["model"])
    if not rows:
        return {}
    try:
        value = _json(rows[0].get("value_json"), {})
        if isinstance(value, dict):
            _HARNESS_SETTINGS.update(value)
    except Exception:
        return {}
    return dict(_HARNESS_SETTINGS)

async def save_harness_settings(value):
    item = dict(value or {})
    _HARNESS_SETTINGS.clear()
    _HARNESS_SETTINGS.update(item)
    if store.configured():
        await store.execute(
            "INSERT INTO harness_settings (setting_key, value_json, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) ON CONFLICT(setting_key) DO UPDATE SET value_json = excluded.value_json, updated_at = CURRENT_TIMESTAMP",
            ["model", json.dumps(item, ensure_ascii=False)])
    return dict(_HARNESS_SETTINGS)

async def get_agent_state(session_id):
    if session_id in _AGENT_STATES:
        return list(_AGENT_STATES[session_id])
    if not store.configured():
        return []
    rows = await _rows("SELECT state_json FROM agent_states WHERE session_id = ? LIMIT 1", [session_id])
    if not rows:
        return []
    state = _json(rows[0].get("state_json"), [])
    if not isinstance(state, list):
        return []
    _AGENT_STATES[session_id] = state
    while len(_AGENT_STATES) > _MAX_AGENT_STATES:
        _AGENT_STATES.pop(next(iter(_AGENT_STATES)), None)
    return list(state)

async def save_agent_state(session_id, items):
    state = list(items or [])
    encoded = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > _MAX_AGENT_STATE_CHARS:
        raise ValueError("Conversation state exceeded the 4 MB replay limit. Start a new conversation or remove older context.")
    _AGENT_STATES[session_id] = state
    while len(_AGENT_STATES) > _MAX_AGENT_STATES:
        _AGENT_STATES.pop(next(iter(_AGENT_STATES)), None)
    if store.configured():
        await store.execute(
            "INSERT INTO agent_states (session_id, state_json, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) ON CONFLICT(session_id) DO UPDATE SET state_json = excluded.state_json, updated_at = CURRENT_TIMESTAMP",
            [session_id, encoded])
    return len(state)

async def save_custom_test(test):
    item = dict(test)
    _cache_custom(item)
    if store.configured():
        await store.execute(
            "INSERT INTO custom_tests (id, category, difficulty, definition_json, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(id) DO UPDATE SET category=excluded.category, difficulty=excluded.difficulty, definition_json=excluded.definition_json, updated_at=CURRENT_TIMESTAMP",
            [item["id"], item.get("category","custom_prompts"), item.get("difficulty","custom"), json.dumps(item, ensure_ascii=False)])
    return item

async def get_custom_test(test_id):
    if test_id in _CUSTOM:
        return dict(_CUSTOM[test_id])
    if not store.configured():
        return None
    rows = await _rows("SELECT definition_json FROM custom_tests WHERE id = ? LIMIT 1", [test_id])
    if not rows:
        return None
    item = _json(rows[0].get("definition_json"), {})
    if item:
        _cache_custom(item)
    return item or None

async def list_custom_tests():
    if not store.configured():
        return [dict(x) for x in _CUSTOM.values()]
    rows = await _rows("SELECT definition_json FROM custom_tests ORDER BY updated_at DESC LIMIT 500")
    result = []
    for row in rows:
        item = _json(row.get("definition_json"), {})
        if item:
            _cache_custom(item)
            result.append(item)
    return result

async def delete_custom_test(test_id):
    existed = test_id in _CUSTOM
    _CUSTOM.pop(test_id, None)
    if store.configured():
        await store.execute("DELETE FROM custom_tests WHERE id = ?", [test_id])
        return True
    return existed

async def create_run(run):
    item = dict(run)
    _cache_run(item)
    if store.configured():
        await store.execute(
            "INSERT INTO test_runs (id, session_id, test_name, status, details_json) VALUES (?, ?, ?, ?, ?)",
            [item["id"], item.get("session_id", item["id"]), item.get("test_id",""), item.get("status","queued"), json.dumps(item, ensure_ascii=False)])
    return item

async def update_run(run_id, changes):
    item = await get_run(run_id)
    if not item:
        return None
    item.update(changes)
    _cache_run(item)
    if store.configured():
        await store.execute("UPDATE test_runs SET status = ?, details_json = ? WHERE id = ?",
                            [item.get("status","unknown"), json.dumps(item, ensure_ascii=False), run_id])
    return item

async def get_run(run_id):
    if run_id in _RUNS:
        return dict(_RUNS[run_id])
    if not store.configured():
        return None
    rows = await _rows("SELECT id, session_id, test_name, status, details_json, created_at FROM test_runs WHERE id = ? LIMIT 1", [run_id])
    if not rows:
        return None
    row = rows[0]
    item = _json(row.get("details_json"), {})
    item.update({"id":row.get("id"),"session_id":row.get("session_id"),"test_id":row.get("test_name"),"status":row.get("status"),"created_at":row.get("created_at")})
    _cache_run(item)
    return item

async def list_runs(limit=100):
    limit = max(1, min(int(limit), 200))
    if not store.configured():
        return list(_RUNS.values())[-limit:][::-1]
    rows = await _rows("SELECT id, session_id, test_name, status, details_json, created_at FROM test_runs ORDER BY created_at DESC LIMIT ?", [limit])
    result = []
    for row in rows:
        item = _json(row.get("details_json"), {})
        item.update({"id":row.get("id"),"session_id":row.get("session_id"),"test_id":row.get("test_name"),"status":row.get("status"),"created_at":row.get("created_at")})
        _cache_run(item)
        result.append(item)
    return result

async def save_run_event(run_id, event):
    item = dict(event)
    _EVENTS.setdefault(run_id, deque(maxlen=500)).append(item)
    if store.configured():
        await store.execute("INSERT INTO run_events (run_id, event_type, event_json) VALUES (?, ?, ?)",
                            [run_id, item.get("type","event"), json.dumps(item, ensure_ascii=False)])

async def list_run_events(run_id):
    if not store.configured():
        return list(_EVENTS.get(run_id, []))
    rows = await _rows("SELECT event_json FROM run_events WHERE run_id = ? ORDER BY id ASC LIMIT 2000", [run_id])
    return [_json(row.get("event_json"), {}) for row in rows]

async def save_chat_message(session_id, role, content):
    if session_id not in _MESSAGES and len(_MESSAGES) >= _MAX_MEMORY_CONVERSATIONS:
        _MESSAGES.pop(next(iter(_MESSAGES)), None)
    memory_content = content[:8000] if isinstance(content, str) else content
    _MESSAGES.setdefault(session_id, []).append({"role":role,"content":memory_content})
    if len(_MESSAGES[session_id]) > 60:
        _MESSAGES[session_id] = _MESSAGES[session_id][-60:]
    if store.configured():
        await store.save_message(session_id, role, content)

async def get_messages(session_id, limit=100):
    if not store.configured():
        return list(_MESSAGES.get(session_id, []))[-max(1,min(limit,200)):]
    rows = await _rows("SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT ?", [session_id, max(1,min(limit,200))])
    result = []
    for row in rows:
        result.append({"role":row.get("role"),"content":_json(row.get("content"),row.get("content")),"created_at":row.get("created_at")})
    return result

async def list_conversations(limit=100):
    if not store.configured():
        ids = list(_MESSAGES.keys())[-max(1,min(limit,200)):]
        return [{"id":sid,"message_count":len(_MESSAGES.get(sid,[]))} for sid in reversed(ids)]
    rows = await _rows("SELECT s.id, s.created_at, (SELECT COUNT(*) FROM messages m WHERE m.session_id=s.id) AS message_count FROM sessions s ORDER BY s.created_at DESC LIMIT ?", [max(1,min(limit,200))])
    return rows

async def save_tool_event(session_id, name, args, output, status="ok"):
    def bounded(value):
        encoded = json.dumps(value, ensure_ascii=False)
        if len(encoded) <= 6000:
            return value
        return {"truncated":True,"preview":encoded[:5800]}
    item = {"session_id":session_id,"tool_name":name,"input":bounded(args),"output":bounded(output),"status":status}
    _TOOL_EVENTS.append(item)
    if store.configured():
        await store.save_tool_event(session_id, name, args, output, status)

async def list_tool_events(session_id=None, limit=200):
    if not store.configured():
        result = list(_TOOL_EVENTS)
        if session_id:
            result = [x for x in result if x["session_id"] == session_id]
        return result[-max(1,min(limit,500)):]
    if session_id:
        rows = await _rows("SELECT session_id, tool_name, input_json, output_json, status, created_at FROM tool_events WHERE session_id = ? ORDER BY id DESC LIMIT ?", [session_id,max(1,min(limit,500))])
    else:
        rows = await _rows("SELECT session_id, tool_name, input_json, output_json, status, created_at FROM tool_events ORDER BY id DESC LIMIT ?", [max(1,min(limit,500))])
    return [{"session_id":r.get("session_id"),"tool_name":r.get("tool_name"),"input":_json(r.get("input_json"),{}),"output":_json(r.get("output_json"),{}),"status":r.get("status"),"created_at":r.get("created_at")} for r in rows]

async def save_metric(session_id, name, value):
    item = {"session_id":session_id,"metric":name,"value":float(value)}
    _METRICS.append(item)
    if store.configured():
        await store.save_metric(session_id, name, value)

async def list_metrics(session_id=None, limit=500):
    limit = max(1,min(limit,2000))
    if not store.configured():
        result = list(_METRICS)
        return [x for x in result if not session_id or x["session_id"] == session_id][-limit:]
    if session_id:
        rows = await _rows("SELECT session_id, metric, value, created_at FROM metrics WHERE session_id = ? ORDER BY id DESC LIMIT ?", [session_id,limit])
    else:
        rows = await _rows("SELECT session_id, metric, value, created_at FROM metrics ORDER BY id DESC LIMIT ?", [limit])
    return rows
