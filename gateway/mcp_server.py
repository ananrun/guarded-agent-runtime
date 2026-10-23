from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from gateway.service import GuardGatewayService


BASE_DIR = Path(__file__).resolve().parent.parent
# MCP 模式下 stdout 要留给协议通信，运行日志写入 logs/ 文件。
package_dir = Path(os.environ["GUARDED_PACKAGE_DIR"]) if os.environ.get("GUARDED_PACKAGE_DIR") else None
service = GuardGatewayService(base_dir=BASE_DIR, package_dir=package_dir)

# 给外部平台暴露的 MCP 服务。QwenPaw 接入后看到的是下面这些 tool。
mcp = FastMCP(
    "guarded-agent-runtime",
    instructions=(
        "这是通用 Guard Gateway。优先调用 guarded_workflow_run 执行声明式工作流；"
        "分步模式先调用 guarded_context_build，所有业务工具必须经 guarded_tool_call，"
        "最终回复必须经 guarded_output_review。"
    ),
)


@mcp.tool()
def guarded_workflow_run(
    workflow_name: str,
    user_request: str,
    user_id: str = "default",
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """执行业务包中声明的任意受控工作流。"""

    return service.run_workflow(
        workflow_name=workflow_name,
        user_request=user_request,
        user_id=user_id,
        inputs=inputs,
    )


@mcp.tool()
def guarded_context_build(user_request: str, user_id: str = "default") -> dict[str, Any]:
    """事前约束：生成受控上下文、工具白名单、禁止动作和业务规则。"""

    # 手动编排模式第一步：先拿 session_id 和可执行边界。
    return service.build_context(user_id=user_id, user_request=user_request)


@mcp.tool()
def guarded_tool_call(
    session_id: str, tool_name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """事中拦截：通用业务工具代理入口。"""

    # 手动编排模式的统一工具代理：外部 Agent 不应绕过这里调用业务工具。
    return service.call_tool(
        session_id=session_id,
        tool_name=tool_name,
        arguments=arguments,
    )


@mcp.tool()
def guarded_output_review(
    session_id: str, final_answer: dict[str, Any]
) -> dict[str, Any]:
    """事后复核：检查最终答案是否可信、合规、可追溯。"""

    # 外部 Agent 准备回复用户前必须调用；失败后再进入下一轮 Agent Loop。
    return service.review_output(session_id=session_id, final_answer=final_answer)


@mcp.tool()
def guarded_attempt_start(session_id: str) -> dict[str, Any]:
    """开启新的 Agent Loop 重试轮次。"""

    # 复核失败后，外部 Agent 每重试一轮先调用它，切分本轮调用日志。
    return service.start_attempt(session_id=session_id)


@mcp.tool()
def guarded_audit_logs(session_id: str | None = None) -> dict[str, Any]:
    """查询工具调用审计日志。"""

    return service.audit_logs(session_id=session_id)


@mcp.tool()
def guarded_policy_reload() -> dict[str, Any]:
    """重新加载本地策略配置。"""

    # 修改 config/*.json 后调用，避免重启 MCP 服务。
    return service.reload_policy()


if __name__ == "__main__":
    mcp.run(transport="stdio")
