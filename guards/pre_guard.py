from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from policies.permissions import UserPermissions
from policies.guard_policies import InGuardPolicy, PreGuardPolicy
from policies.rules import BusinessRules
from tools.tool_registry import ToolRegistry


@dataclass
class PreGuard:
    # Pre-Guard 不调用大模型，只做确定性的上下文装配。
    rules: BusinessRules
    permissions: UserPermissions
    registry: ToolRegistry
    pre_policy: PreGuardPolicy
    in_policy: InGuardPolicy

    def build_context(self, user_request: str) -> dict[str, Any]:
        # 任务识别、权限加载、工具白名单和禁止动作都在这里完成。
        # 外部 Agent 收到这个 context 后，应该只围绕这些信息做规划。
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
                "forbidden_actions": sorted(self.in_policy.forbidden_actions),
            },
            "model_instructions": self.pre_policy.model_instructions,
        }

    def _classify_task(self, user_request: str) -> str:
        # 这里先用关键词识别任务类型，后续可替换为更复杂的分类器。
        for task_type, keywords in self.pre_policy.task_keywords.items():
            if any(keyword in user_request for keyword in keywords):
                return task_type
        return "general_task"
