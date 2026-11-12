"""Cloudflare D1 adapter. Inputs: SQL and parameters. Output: D1 result or no-op if unconfigured."""
import json
import logging
import httpx
from .config import settings

log = logging.getLogger(__name__)
_client = None

def configured():
    return bool(settings.cf_account_id and settings.cf_api_token and settings.d1_database_id)

async def start_store():
    global _client
    if not configured():
        log.warning("D1 is not configured; persistence is disabled.")
        return
    _client = httpx.AsyncClient(timeout=15, limits=httpx.Limits(max_connections=2, max_keepalive_connections=1))
    statements = [
        "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS tool_events (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, tool_name TEXT, input_json TEXT, output_json TEXT, status TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS test_runs (id TEXT PRIMARY KEY, session_id TEXT, test_name TEXT, status TEXT, details_json TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE IF NOT EXISTS metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, metric TEXT, value REAL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    ]
    for sql in statements:
        await execute(sql)

async def execute(sql, params=None):
    if not configured() or _client is None:
        return None
    url = f"https://api.cloudflare.com/client/v4/accounts/{settings.cf_account_id}/d1/database/{settings.d1_database_id}/query"
    response = await _client.post(url, headers={"Authorization": f"Bearer {settings.cf_api_token}"}, json={"sql": sql, "params": params or []})
    response.raise_for_status()
    body = response.json()
    if not body.get("success"):
        raise RuntimeError(f"D1 query failed: {body.get('errors')}")
    return body.get("result")

async def save_message(session_id, role, content):
    await execute("INSERT INTO sessions (id) VALUES (?) ON CONFLICT(id) DO NOTHING", [session_id])
    await execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", [session_id, role, json.dumps(content, ensure_ascii=False)])

async def save_tool_event(session_id, name, args, output, status="ok"):
    await execute("INSERT INTO tool_events (session_id, tool_name, input_json, output_json, status) VALUES (?, ?, ?, ?, ?)",
                  [session_id, name, json.dumps(args), json.dumps(output, ensure_ascii=False), status])

async def save_metric(session_id, name, value):
    await execute("INSERT INTO metrics (session_id, metric, value) VALUES (?, ?, ?)", [session_id, name, float(value)])

async def close_store():
    global _client
    if _client:
        await _client.aclose()
        _client = None
