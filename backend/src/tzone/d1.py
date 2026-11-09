from typing import Any

import httpx


class D1Error(RuntimeError):
    pass


class D1Client:
    """Small I/O boundary: SQL + parameters in, decoded D1 result out."""

    def __init__(self, account_id: str, database_id: str, api_token: str) -> None:
        self._url = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
            f"/d1/database/{database_id}/query"
        )
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=httpx.Timeout(20.0),
        )

    async def query(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        encoded_params = [None if value is None else str(value) for value in (params or [])]
        response = await self._client.post(self._url, json={"sql": sql, "params": encoded_params})
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise D1Error(str(payload.get("errors") or "D1 query failed"))
        results = payload.get("result") or []
        if not results:
            return []
        return results[0].get("results") or []

    async def execute(self, sql: str, params: list[Any] | None = None) -> None:
        await self.query(sql, params)

    async def close(self) -> None:
        await self._client.aclose()
