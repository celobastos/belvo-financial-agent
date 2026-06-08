import asyncio

from belvo_finance_agent.mcp_client import MCPClient


class FakeSessionMCPClient(MCPClient):
    def __init__(self):
        self._initialized = False
        self._session_id = None
        self.calls = []

    async def initialize(self):
        self.calls.append(("initialize", None))
        self._session_id = "session-123"
        self._initialized = True
        return {}

    async def _request(self, method, params, skip_initialize=False):
        self.calls.append((method, params))
        return {"content": [{"type": "text", "text": "[]"}]}


def test_call_tool_initializes_session_first() -> None:
    client = FakeSessionMCPClient()
    result = asyncio.run(client.call_tool("list_accounts", {}))
    assert result == []
    assert client.calls[0][0] == "initialize"
    assert client.calls[1][0] == "tools/call"
    assert client._session_id == "session-123"
