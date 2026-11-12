"""Cloudflare D1 connectivity only. No schema creation, table access, or persistence."""
import httpx
from .config import settings

_client = None


def configured():
    return bool(settings.cf_account_id and settings.cf_api_token and settings.d1_database_id)


async def start_store():
    global _client
    if configured():
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(15, connect=5),
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        )


async def check_connection():
    if not configured() or _client is None:
        return False
    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        + settings.cf_account_id
        + "/d1/database/"
        + settings.d1_database_id
        + "/query"
    )
    try:
        response = await _client.post(
            url,
            headers={"Authorization": "Bearer " + settings.cf_api_token},
            json={"sql": "SELECT 1 AS connected", "params": []},
        )
        response.raise_for_status()
        payload = response.json()
        return bool(payload.get("success"))
    except (httpx.HTTPError, ValueError):
        return False


async def close_store():
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
