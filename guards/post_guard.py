from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from policies.permissions import UserPermissions
from policies.guard_policies import PostGuardPolicy
from policies.rules import BusinessRules


@dataclass
class ReviewResult:
    # passed=False 时，reasons 会反馈给外部 Agent 作为下一轮重试依据。
    passed: bool
    reasons: list[str]


@dataclass
class PostGuard:
    # Post-Guard 只看最终输出、真实工具证据和本轮调用日志。
    rules: BusinessRules
    permissions: UserPermissions
    policy: PostGuardPolicy

    def review(
        self,
        final_answer: dict[str, Any] | None,
        observations: list[dict[str, Any]],
        call_log: list[dict[str, Any]],
    ) -> ReviewResult:
        reasons: list[str] = []
        if final_answer is None:
            return ReviewResult(False, ["Agent 未生成最终结果。"])

        # 金额类判断以 calculate_reimbursement 的真实返回为准。
        calculation = self._latest_result(observations, "calculate_reimbursement")
        # 本轮被 In-Guard 拦截过的调用，可以配置为直接导致复核失败。
        blocked_calls = [item for item in call_log if not item["allowed"]]

        if self.policy.block_on_intercepted_tool_call and blocked_calls:
            reasons.extend(f"存在被事中拦截的工具调用：{item['reason']}" for item in blocked_calls)
        # 防止 Agent 没有调用必要工具，却直接编造审核结论。
        for tool_name in self.policy.required_source_tools:
            if not self._latest_result(observations, tool_name):
                reasons.append(f"最终结果缺少 {tool_name} 的真实工具返回依据。")

        # 越权承诺通常体现在自然语言里，因此这里用配置化短语做确定性扫描。
        message = str(final_answer.get("message", ""))
        for phrase in self.policy.forbidden_output_phrases:
            if phrase in message:
                reasons.append(f"输出包含越权承诺：{phrase}。")

        if calculation:
            # 最终报告里的金额必须和工具计算结果一致。
            expected_a = Decimal(str(calculation["project_a_reimbursable"]))
            actual_a = Decimal(str(final_answer.get("project_a_reimbursable", "0")))
            if actual_a != expected_a:
                reasons.append(f"项目A金额不一致：期望 {expected_a}，实际 {actual_a}。")

            expected_other = Decimal(str(calculation["other_channel_amount"]))
            actual_other = Decimal(str(final_answer.get("other_channel_amount", "0")))
            if actual_other != expected_other:
                reasons.append(f"其他渠道金额不一致：期望 {expected_other}，实际 {actual_other}。")

            # 不可计入项目A的费用不能漏报，也不能被错误移入项目A。
            reported_blocked = {
                item.get("name") for item in final_answer.get("not_allowed_in_project_a", [])
            }
            expected_blocked = {
                item.get("name") for item in calculation.get("not_allowed_in_project_a", [])
            }
            if reported_blocked != expected_blocked:
                reasons.append("不可计入项目A的费用列表与规则计算结果不一致。")

        # 输出字段检查保证外部平台最终回复结构稳定。
        missing = [field for field in self.policy.required_output_fields if field not in final_answer]
        if missing:
            reasons.append(f"输出格式缺少字段：{', '.join(missing)}。")

        return ReviewResult(passed=not reasons, reasons=reasons)

    @staticmethod
    def _latest_result(observations: list[dict[str, Any]], tool_name: str) -> dict[str, Any]:
        # 同一个工具可能在 Agent Loop 中被调用多次，复核使用最近一次成功结果。
        for item in reversed(observations):
            if item.get("tool") == tool_name and item.get("allowed"):
                return item["result"]
        return {}
