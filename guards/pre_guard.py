from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from policies.permissions import UserPermissions
from policies.rules import BusinessRules
from tools.tool_registry import ToolRegistry


@dataclass
class PreGuard:
    rules: BusinessRules
    permissions: UserPermissions
    registry: ToolRegistry

    def build_context(self, user_request: str) -> dict[str, Any]:
        task_type = self._classify_task(user_request)
        allowed_tools = self.registry.allowed_tool_names_for_permissions(self.permissions)

        return {
            "task_type": task_type,
            "user_request": user_request,
            "user": {
                "user_id": self.permissions.user_id,
                "roles": self.permissions.roles,
                "allowed_actions": sorted(self.permissions.allowed_actions),
            },
            "business_rules": self.rules.to_dict(),
            "tool_policy": {
                "allowed_tools": allowed_tools,
                "forbidden_actions": sorted(self.rules.forbidden_actions),
            },
            "model_instructions": [
                "只能调用工具白名单中的工具。",
                "不得编造工具没有返回的数据。",
                "不得输出付款、预算修改、票据修改等越权承诺。",
                "必须输出项目A金额、其他渠道金额、不可计入项目A费用和异常项。",
            ],
        }

    @staticmethod
    def _classify_task(user_request: str) -> str:
        if "报销" in user_request or "差旅" in user_request:
            return "travel_expense_audit"
        return "general_task"
