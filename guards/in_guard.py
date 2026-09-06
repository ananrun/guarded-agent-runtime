from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from policies.permissions import UserPermissions
from policies.guard_policies import InGuardPolicy
from policies.rules import BusinessRules
from runtime.executor import ToolCall, ToolResult
from runtime.sandbox import Sandbox
from tools.tool_registry import ToolRegistry


@dataclass
class InGuard:
    # In-Guard 是代码级硬拦截层，不相信外部 Agent 自己判断是否合规。
    rules: BusinessRules
    permissions: UserPermissions
    registry: ToolRegistry
    policy: InGuardPolicy
    sandbox: Sandbox = field(default_factory=Sandbox)
    call_log: list[dict[str, Any]] = field(default_factory=list)

    def execute(self, call: ToolCall, allowed_tools: list[str]) -> ToolResult:
        # 所有工具执行前先过校验；失败时直接返回拦截结果，不进入真实工具。
        validation_error = self._validate(call, allowed_tools)
        if validation_error:
            result = ToolResult(
                tool=call.name,
                allowed=False,
                result=None,
                reason=validation_error,
            )
            self._log(call, result)
            return result

        tool = self.registry.get(call.name)
        try:
            # 真实工具只在校验通过后进入沙箱执行。
            output = self.sandbox.run(tool.func, call.arguments)
            result = ToolResult(tool=call.name, allowed=True, result=output, reason=None)
        except Exception as exc:  # pragma: no cover - 演示兜底
            result = ToolResult(
                tool=call.name,
                allowed=False,
                result=None,
                reason=f"工具执行失败：{exc}",
            )

        self._log(call, result)
        return result

    def _validate(self, call: ToolCall, allowed_tools: list[str]) -> str | None:
        # 先拦禁止动作，保证 approve_payment / modify_budget 这类动作不会被误执行。
        if call.name in self.policy.forbidden_actions:
            return f"拦截原因：{call.name} 属于禁止动作。"
        # 再拦未注册工具，避免 Agent 编造工具名。
        if self.policy.enforce_registered_tools and call.name not in self.registry.names():
            return f"拦截原因：工具 {call.name} 未注册。"
        # 白名单来自 Pre-Guard，限制当前任务可用的工具集合。
        if self.policy.enforce_tool_whitelist and call.name not in allowed_tools:
            return f"拦截原因：工具 {call.name} 不在当前任务工具白名单中。"

        tool = self.registry.get(call.name)
        # 权限来自用户配置，和工具所需权限逐项匹配。
        if (
            self.policy.enforce_user_permissions
            and tool.required_permission not in self.permissions.allowed_actions
        ):
            return f"拦截原因：当前用户缺少权限 {tool.required_permission}。"

        # Schema 校验用于拦截缺参、错参和非法枚举值。
        if self.policy.enforce_schema_validation:
            schema_error = tool.validate_arguments(call.arguments)
            if schema_error:
                return f"拦截原因：参数不合法，{schema_error}"
        return None

    def _log(self, call: ToolCall, result: ToolResult) -> None:
        # call_log 记录允许和拦截的全部调用，给审计和 Post-Guard 使用。
        self.call_log.append(
            {
                "tool": call.name,
                "arguments": call.arguments,
                "allowed": result.allowed,
                "reason": result.reason,
            }
        )
