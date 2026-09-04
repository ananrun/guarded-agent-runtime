from __future__ import annotations

import json
from pathlib import Path

from gateway.service import GuardGatewayService


def main() -> None:
    service = GuardGatewayService(base_dir=Path(__file__).resolve().parent)

    auto_audit = service.audit_expense(
        user_id="auditor_001",
        user_request="帮我审核报销单",
    )

    context_response = service.build_context(
        user_id="auditor_001",
        user_request="帮我审核报销单",
    )
    session_id = context_response["session_id"]
    blocked = service.call_tool(session_id, "approve_payment", {"expense_id": "EXP-2026-001"})
    unsafe_review = service.review_output(
        session_id,
        {
            "status": "unsafe",
            "message": "项目A可全额报销 30236.01 元，已提交付款。",
            "project_a_reimbursable": 30236.01,
            "other_channel_amount": 0,
            "not_allowed_in_project_a": [],
            "exceptions": [],
            "source_tools": ["read_expense_form"],
        },
    )

    print(
        json.dumps(
            {
                "说明": "auto_audit 模拟 QwenPaw 只调用一个工具 guarded_expense_audit；manual_violation 模拟分步调试时的违规拦截。",
                "auto_audit": auto_audit,
                "manual_violation": {
                    "context_build": context_response,
                    "blocked_tool_call": blocked,
                    "review_output": unsafe_review,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
