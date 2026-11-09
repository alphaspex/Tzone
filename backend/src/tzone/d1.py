from typing import Any, Iterable

import httpx


class D1Error(RuntimeError):
    pass


class D1Client:
    """SQL + parameters in, decoded D1 results out."""

    def __init__(self, account_id: str, database_id: str, api_token: str) -> None:
        self._url = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
            f"/d1/database/{database_id}/query"
        )
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    @staticmethod
    def _params(values: Iterable[Any]) -> list[Any]:
        return [None if value is None else str(value) for value in values]

    async def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        response = await self._client.post(
            self._url, json={"sql": sql, "params": self._params(params)}
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise D1Error(str(payload.get("errors") or "D1 query failed"))
        results = payload.get("result") or []
        return results[0].get("results") or [] if results else []

    async def batch(self, statements: list[tuple[str, Iterable[Any]]]) -> None:
        if not statements:
            return
        response = await self._client.post(
            self._url,
            json={"batch": [
                {"sql": sql, "params": self._params(params)}
                for sql, params in statements
            ]},
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise D1Error(str(payload.get("errors") or "D1 batch failed"))

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        await self.query(sql, params)

    async def close(self) -> None:
        await self._client.aclose()
