"""Meta Model API Responses transport. Input: native Responses payload. Output: HTTP stream or parsed SSE events."""
import json
import httpx
from .config import settings

_client = None


class ProviderError(RuntimeError):
    def __init__(self, status_code, detail):
        self.status_code = int(status_code)
        self.detail = detail
        super().__init__(f"Meta Model API HTTP {self.status_code}: {detail}")


async def start_provider():
    global _client
    _client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.request_timeout, connect=15),
        limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
    )


async def close_provider():
    global _client
    if _client:
        await _client.aclose()
        _client = None


async def open_response(payload, path="responses", method="POST"):
    if not settings.meta_api_key:
        raise RuntimeError("Missing MODEL_API_KEY environment variable in Deplexo.")
    if _client is None:
        raise RuntimeError("Meta API client is not initialized.")
    url = settings.meta_base_url.rstrip("/") + "/" + str(path).lstrip("/")
    request = _client.build_request(
        method,
        url,
        headers={
            "Authorization": f"Bearer {settings.meta_api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if payload.get("stream") else "application/json",
        },
        json=payload if method.upper() != "GET" else None,
    )
    return await _client.send(request, stream=True)


async def stream_events(payload):
    response = await open_response(payload)
    try:
        if response.status_code >= 400:
            detail = (await response.aread()).decode("utf-8", "replace")[:4000]
            raise ProviderError(response.status_code, detail)
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
    finally:
        await response.aclose()
