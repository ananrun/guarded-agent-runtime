from __future__ import annotations

import asyncio
import argparse
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main() -> None:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="验证任意业务包的 MCP 工作流")
    parser.add_argument(
        "--package-dir",
        default=base_dir / "examples" / "packages",
        type=Path,
        help="包含一个或多个业务包的目录",
    )
    parser.add_argument("--demo", type=Path, help="指定业务包的 demo.json；默认取第一个")
    args = parser.parse_args()
    package_dir = args.package_dir.resolve()
    demo_path = args.demo or next(package_dir.rglob("demo.json"), None)
    if demo_path is None:
        raise FileNotFoundError(f"未找到 demo.json：{package_dir}")
    with demo_path.open(encoding="utf-8") as fh:
        request = json.load(fh)["request"]
    # 验证调用方只提供自然语言请求时，框架仍可按关键词自动匹配业务包。
    request.pop("workflow_name", None)
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "gateway.mcp_server"],
        cwd=str(base_dir),
        env={"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1", "GUARDED_PACKAGE_DIR": str(package_dir)},
    )

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("guarded_workflow_run", request)

    print(
        json.dumps(
            {
                "tool_count": len(tools.tools),
                "tool_names": [tool.name for tool in tools.tools],
                "result": [item.model_dump() for item in result.content],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
