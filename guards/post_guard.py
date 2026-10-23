from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from policies.permissions import UserPermissions
from policies.guard_policies import PostGuardPolicy


@dataclass
class ReviewResult:
    # passed=False 时，reasons 会反馈给外部 Agent 作为下一轮重试依据。
    passed: bool
    reasons: list[str]


@dataclass
class PostGuard:
    # Post-Guard 只看最终输出、真实工具证据和本轮调用日志。
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

        # 本轮被 In-Guard 拦截过的调用，可以配置为直接导致复核失败。
        blocked_calls = [item for item in call_log if not item["allowed"]]

        if self.policy.block_on_intercepted_tool_call and blocked_calls:
            reasons.extend(f"存在被事中拦截的工具调用：{item['reason']}" for item in blocked_calls)
        # 需要哪些来源证据、哪些字段，由配置决定；框架不解释业务字段。
        for tool_name in self.policy.required_source_tools:
            if not self._latest_result(observations, tool_name):
                reasons.append(f"最终结果缺少 {tool_name} 的真实工具返回依据。")

        # 越权承诺通常体现在自然语言里，因此这里用配置化短语做确定性扫描。
        message = str(final_answer.get("message", ""))
        for phrase in self.policy.forbidden_output_phrases:
            if phrase in message:
                reasons.append(f"输出包含越权承诺：{phrase}。")

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
