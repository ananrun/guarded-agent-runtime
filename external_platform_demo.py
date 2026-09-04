from __future__ import annotations

import json
from pathlib import Path

from gateway.service import GuardGatewayService


def main() -> None:
    service = GuardGatewayService(base_dir=Path(__file__).resolve().parent)

    context_response = service.build_context(
        user_id="auditor_001",
        user_request="帮我审核这张差旅报销单，能报的直接生成审核意见。",
    )
    session_id = context_response["session_id"]

    # 这里模拟 QwenPaw / DeerFlow 已经被配置为只调用网关工具。
    form = service.call_tool(session_id, "read_expense_form", {"expense_id": "EXP-2026-001"})
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

    retry = service.start_attempt(session_id)
    invoice = service.call_tool(session_id, "check_invoice", {"expense_id": "EXP-2026-001"})
    calculation = service.call_tool(
        session_id,
        "calculate_reimbursement",
        {"expense_id": "EXP-2026-001", "project": "project_a"},
    )
    opinion = service.call_tool(
        session_id,
        "generate_audit_opinion",
        {
            "expense_id": "EXP-2026-001",
            "calculation": calculation["result"],
            "include_payment_commitment": False,
        },
    )

    final_answer = {
        "status": "passed",
        "message": opinion["result"]["opinion"],
        "project_a_reimbursable": calculation["result"]["project_a_reimbursable"],
        "other_channel_amount": calculation["result"]["other_channel_amount"],
        "not_allowed_in_project_a": calculation["result"]["not_allowed_in_project_a"],
        "exceptions": calculation["result"]["exceptions"],
        "source_tools": [
            "read_expense_form",
            "check_invoice",
            "calculate_reimbursement",
            "generate_audit_opinion",
        ],
        "forbidden_commitments": [],
    }
    review = service.review_output(session_id, final_answer)

    print(
        json.dumps(
            {
                "说明": "这是外部平台接入后的调用顺序模拟，不是平台自动具备网关能力。",
                "context_build": context_response,
                "first_attempt": {
                    "tool_calls": [form, blocked],
                    "review_output": unsafe_review,
                },
                "retry_attempt": {
                    "attempt_start": retry,
                    "tool_calls": [invoice, calculation, opinion],
                    "review_output": review,
                },
                "audit_logs": service.audit_logs(session_id),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
