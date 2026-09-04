from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main() -> None:
    base_dir = Path(__file__).resolve().parent
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "gateway.mcp_server"],
        cwd=str(base_dir),
        env={"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"},
    )

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            audit = await session.call_tool(
                "guarded_expense_audit",
                {
                    "user_request": "帮我审核这张差旅报销单，能报的直接生成审核意见。",
                    "user_id": "auditor_001",
                },
            )

    print(
        json.dumps(
            {
                "tool_count": len(tools.tools),
                "tool_names": [tool.name for tool in tools.tools],
                "audit_call": [item.model_dump() for item in audit.content],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
