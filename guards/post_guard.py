from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from policies.permissions import UserPermissions
from policies.rules import BusinessRules


@dataclass
class ReviewResult:
    passed: bool
    reasons: list[str]


@dataclass
class PostGuard:
    rules: BusinessRules
    permissions: UserPermissions

    def review(
        self,
        final_answer: dict[str, Any] | None,
        observations: list[dict[str, Any]],
        call_log: list[dict[str, Any]],
    ) -> ReviewResult:
        reasons: list[str] = []
        if final_answer is None:
            return ReviewResult(False, ["Agent 未生成最终结果。"])

        calculation = self._latest_result(observations, "calculate_reimbursement")
        opinion = self._latest_result(observations, "generate_audit_opinion")
        blocked_calls = [item for item in call_log if not item["allowed"]]

        if blocked_calls:
            reasons.extend(f"存在被事中拦截的工具调用：{item['reason']}" for item in blocked_calls)
        if not calculation:
            reasons.append("最终结果缺少 calculate_reimbursement 的真实工具返回依据。")
        if not opinion:
            reasons.append("最终结果缺少 generate_audit_opinion 的真实工具返回依据。")

        message = str(final_answer.get("message", ""))
        forbidden_phrases = ["已提交付款", "已付款", "已修改预算", "预算调整"]
        for phrase in forbidden_phrases:
            if phrase in message:
                reasons.append(f"输出包含越权承诺：{phrase}。")

        if calculation:
            expected_a = Decimal(str(calculation["project_a_reimbursable"]))
            actual_a = Decimal(str(final_answer.get("project_a_reimbursable", "0")))
            if actual_a != expected_a:
                reasons.append(f"项目A金额不一致：期望 {expected_a}，实际 {actual_a}。")

            expected_other = Decimal(str(calculation["other_channel_amount"]))
            actual_other = Decimal(str(final_answer.get("other_channel_amount", "0")))
            if actual_other != expected_other:
                reasons.append(f"其他渠道金额不一致：期望 {expected_other}，实际 {actual_other}。")

            reported_blocked = {
                item.get("name") for item in final_answer.get("not_allowed_in_project_a", [])
            }
            expected_blocked = {
                item.get("name") for item in calculation.get("not_allowed_in_project_a", [])
            }
            if reported_blocked != expected_blocked:
                reasons.append("不可计入项目A的费用列表与规则计算结果不一致。")

        required_fields = [
            "project_a_reimbursable",
            "other_channel_amount",
            "not_allowed_in_project_a",
            "exceptions",
            "source_tools",
        ]
        missing = [field for field in required_fields if field not in final_answer]
        if missing:
            reasons.append(f"输出格式缺少字段：{', '.join(missing)}。")

        return ReviewResult(passed=not reasons, reasons=reasons)

    @staticmethod
    def _latest_result(observations: list[dict[str, Any]], tool_name: str) -> dict[str, Any]:
        for item in reversed(observations):
            if item.get("tool") == tool_name and item.get("allowed"):
                return item["result"]
        return {}
