from __future__ import annotations

import asyncio

from .mcp_client import MCPClient


async def main_async() -> None:
    client = MCPClient()
    await client.initialize()
    tools = await client.list_tools()
    print("Available tools:")
    for tool in tools:
        print(f"- {tool.get('name')}: {tool.get('description', '')}")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
