from __future__ import annotations

from typing import Any


def build_mock_system_prompt(model_context: dict[str, Any]) -> str:
    allowed = ", ".join(model_context["tool_policy"]["allowed_tools"])
    forbidden = ", ".join(model_context["tool_policy"]["forbidden_actions"])
    return (
        "你是差旅报销审核 Agent。只能依据注入上下文和真实工具结果回答。"
        f"允许工具：{allowed}。禁止动作：{forbidden}。"
        "不得承诺付款、修改预算或修改票据。"
    )
