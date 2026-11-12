"""Z.ai streaming adapter. Input: OpenAI-compatible request payload. Output: parsed SSE data objects."""
import json
import httpx
from .config import settings

_client = None

async def start_provider():
    global _client
    _client = httpx.AsyncClient(timeout=httpx.Timeout(settings.request_timeout, connect=15),
        limits=httpx.Limits(max_connections=2, max_keepalive_connections=1))

async def close_provider():
    global _client
    if _client:
        await _client.aclose()
        _client = None

async def stream_chat(payload):
    if not settings.zai_api_key:
        raise RuntimeError("Missing ZAI_API_KEY environment variable")
    if _client is None:
        raise RuntimeError("Provider client is not initialized")
    url = settings.zai_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.zai_api_key}", "Content-Type": "application/json"}
    async with _client.stream("POST", url, headers=headers, json=payload) as response:
        if response.status_code >= 400:
            detail = (await response.aread()).decode("utf-8", "replace")[:2000]
            raise RuntimeError(f"Z.ai HTTP {response.status_code}: {detail}")
        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                yield json.loads(data)
            except json.JSONDecodeError:
                continue
