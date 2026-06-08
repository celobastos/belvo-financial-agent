from __future__ import annotations

import json
import logging
from itertools import count
from typing import Any

try:
    import httpx
except ModuleNotFoundError:
    httpx = None

from .config import Settings, get_settings
from .models import Account, Owner, Transaction

logger = logging.getLogger(__name__)


class MCPError(RuntimeError):
    pass


class MCPClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._ids = count(1)
        self._session_id: str | None = None
        self._initialized = False

    @property
    def headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.settings.mcp_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["mcp-session-id"] = self._session_id
        return headers

    async def initialize(self) -> dict[str, Any]:
        result = await self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "belvo-finance-agent", "version": "0.1.0"},
            },
            skip_initialize=True,
        )
        if self._session_id:
            await self._send_notification("notifications/initialized", {})
        self._initialized = True
        return result

    async def list_tools(self) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        result = await self._request("tools/list", {})
        tools = result.get("tools", result if isinstance(result, list) else [])
        return tools if isinstance(tools, list) else []

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        await self._ensure_initialized()
        result = await self._request("tools/call", {"name": name, "arguments": arguments or {}})
        return self._unwrap_tool_result(result)

    async def get_owners(self, filters: dict[str, Any] | None = None) -> list[Owner]:
        rows = await self._fetch_all("get_owners", filters or {})
        return [Owner(**self._with_raw(row)) for row in rows]

    async def list_accounts(self, filters: dict[str, Any] | None = None) -> list[Account]:
        rows = await self._fetch_all("list_accounts", filters or {})
        return [Account(**self._with_raw(row)) for row in rows]

    async def list_transactions(self, filters: dict[str, Any] | None = None) -> list[Transaction]:
        rows = await self._fetch_all("list_transactions", filters or {})
        return [Transaction(**self._with_raw(row)) for row in rows]

    async def _fetch_all(self, tool_name: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        all_rows: list[dict[str, Any]] = []
        page_size = self.settings.mcp_page_size

        for page in range(1, self.settings.mcp_max_pages + 1):
            params = {"page": page, "page_size": page_size, **filters}
            payload = await self.call_tool(tool_name, params)
            rows = self._extract_rows(payload)
            all_rows.extend(rows)

            if len(rows) < page_size:
                break

        return all_rows

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()

    async def _request(self, method: str, params: dict[str, Any], skip_initialize: bool = False) -> dict[str, Any]:
        if httpx is None:
            raise MCPError("httpx is not installed. Run: python -m pip install -e \".[dev]\"")

        if not skip_initialize and method != "initialize":
            await self._ensure_initialized()

        body = {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params}
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.post(self.settings.mcp_url, headers=self.headers, json=body)
            except httpx.HTTPError as exc:
                raise MCPError(
                    f"Could not reach MCP at {self.settings.mcp_url}. "
                    "Start it with: docker run -d -p 8000:8000 --name ofda-mcp "
                    "gniparcs/intelligence-se-hiring-ofda-mcp:latest"
                ) from exc

        if response.headers.get("mcp-session-id"):
            self._session_id = response.headers["mcp-session-id"]

        if response.status_code >= 400:
            raise MCPError(f"MCP request failed ({response.status_code}): {response.text[:500]}")

        payload = self._parse_response(response)
        if "error" in payload:
            raise MCPError(f"MCP {method} error: {payload['error']}")
        result = payload.get("result")
        return result if isinstance(result, dict) else {"result": result}

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        if httpx is None:
            raise MCPError("httpx is not installed. Run: python -m pip install -e \".[dev]\"")

        body = {"jsonrpc": "2.0", "method": method, "params": params}
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.post(self.settings.mcp_url, headers=self.headers, json=body)
            except httpx.HTTPError as exc:
                raise MCPError(
                    f"Could not reach MCP at {self.settings.mcp_url}. "
                    "Start it with: docker run -d -p 8000:8000 --name ofda-mcp "
                    "gniparcs/intelligence-se-hiring-ofda-mcp:latest"
                ) from exc

        if response.status_code >= 400:
            raise MCPError(f"MCP notification failed ({response.status_code}): {response.text[:500]}")

    def _parse_response(self, response: httpx.Response) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type or response.text.lstrip().startswith("event:"):
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    data = line.removeprefix("data:").strip()
                    if data and data != "[DONE]":
                        return json.loads(data)
            raise MCPError("MCP returned an empty event stream response.")
        return response.json()

    def _unwrap_tool_result(self, result: dict[str, Any]) -> Any:
        if "content" not in result:
            return result.get("result", result)

        content = result.get("content") or []
        if not content:
            return []

        first = content[0]
        if isinstance(first, dict) and first.get("type") == "text":
            text = first.get("text", "")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        return content

    def _extract_rows(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("results", "data", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            if payload and all(not isinstance(value, list) for value in payload.values()):
                return [payload]
        logger.warning("Could not extract rows from MCP payload shape: %s", type(payload))
        return []

    def _with_raw(self, row: dict[str, Any]) -> dict[str, Any]:
        return {**row, "raw": row}
