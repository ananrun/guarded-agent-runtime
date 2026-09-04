from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from gateway.service import GuardGatewayService


BASE_DIR = Path(__file__).resolve().parent.parent
service = GuardGatewayService(base_dir=BASE_DIR)

mcp = FastMCP(
    "guarded-agent-runtime",
    instructions=(
        "这是 Guard Gateway 的 MCP 接入层。外部 Agent 必须先调用 "
        "guarded_context_build 获取 session_id，再携带 session_id 调用受控业务工具，"
        "最终答案必须调用 guarded_output_review 复核。"
    ),
)


@mcp.tool()
def guarded_context_build(user_id: str, user_request: str) -> dict[str, Any]:
    """事前约束：生成受控上下文、工具白名单、禁止动作和业务规则。"""

    return service.build_context(user_id=user_id, user_request=user_request)


@mcp.tool()
def guarded_tool_call(
    session_id: str, tool_name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """事中拦截：通用业务工具代理入口。"""

    return service.call_tool(
        session_id=session_id,
        tool_name=tool_name,
        arguments=arguments,
    )


@mcp.tool()
def guard_read_expense_form(session_id: str, expense_id: str) -> dict[str, Any]:
    """受控读取报销单。"""

    return service.call_tool(
        session_id=session_id,
        tool_name="read_expense_form",
        arguments={"expense_id": expense_id},
    )


@mcp.tool()
def guard_check_invoice(session_id: str, expense_id: str) -> dict[str, Any]:
    """受控核验发票。"""

    return service.call_tool(
        session_id=session_id,
        tool_name="check_invoice",
        arguments={"expense_id": expense_id},
    )


@mcp.tool()
def guard_calculate_reimbursement(
    session_id: str, expense_id: str, project: str
) -> dict[str, Any]:
    """受控计算报销金额。"""

    return service.call_tool(
        session_id=session_id,
        tool_name="calculate_reimbursement",
        arguments={"expense_id": expense_id, "project": project},
    )


@mcp.tool()
def guard_generate_audit_opinion(
    session_id: str,
    expense_id: str,
    calculation: dict[str, Any],
    include_payment_commitment: bool = False,
) -> dict[str, Any]:
    """受控生成审核意见。"""

    return service.call_tool(
        session_id=session_id,
        tool_name="generate_audit_opinion",
        arguments={
            "expense_id": expense_id,
            "calculation": calculation,
            "include_payment_commitment": include_payment_commitment,
        },
    )


@mcp.tool()
def guarded_output_review(
    session_id: str, final_answer: dict[str, Any]
) -> dict[str, Any]:
    """事后复核：检查最终答案是否可信、合规、可追溯。"""

    return service.review_output(session_id=session_id, final_answer=final_answer)


@mcp.tool()
def guarded_attempt_start(session_id: str) -> dict[str, Any]:
    """开启新的 Agent Loop 重试轮次。"""

    return service.start_attempt(session_id=session_id)


@mcp.tool()
def guarded_audit_logs(session_id: str | None = None) -> dict[str, Any]:
    """查询工具调用审计日志。"""

    return service.audit_logs(session_id=session_id)


@mcp.tool()
def guarded_policy_reload() -> dict[str, Any]:
    """重新加载本地策略配置。"""

    return service.reload_policy()


if __name__ == "__main__":
    mcp.run(transport="stdio")
