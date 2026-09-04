from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from policies.permissions import UserPermissions
from policies.rules import BusinessRules
from runtime.executor import ToolCall, ToolResult
from runtime.sandbox import Sandbox
from tools.tool_registry import ToolRegistry


@dataclass
class InGuard:
    rules: BusinessRules
    permissions: UserPermissions
    registry: ToolRegistry
    sandbox: Sandbox = field(default_factory=Sandbox)
    call_log: list[dict[str, Any]] = field(default_factory=list)

    def execute(self, call: ToolCall, allowed_tools: list[str]) -> ToolResult:
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
        if call.name in self.rules.forbidden_actions:
            return f"拦截原因：{call.name} 属于禁止动作。"
        if call.name not in self.registry.names():
            return f"拦截原因：工具 {call.name} 未注册。"
        if call.name not in allowed_tools:
            return f"拦截原因：工具 {call.name} 不在当前任务工具白名单中。"

        tool = self.registry.get(call.name)
        if tool.required_permission not in self.permissions.allowed_actions:
            return f"拦截原因：当前用户缺少权限 {tool.required_permission}。"

        schema_error = tool.validate_arguments(call.arguments)
        if schema_error:
            return f"拦截原因：参数不合法，{schema_error}"
        return None

    def _log(self, call: ToolCall, result: ToolResult) -> None:
        self.call_log.append(
            {
                "tool": call.name,
                "arguments": call.arguments,
                "allowed": result.allowed,
                "reason": result.reason,
            }
        )
