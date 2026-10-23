from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from framework.packages import PackageCatalog
from policies.permissions import UserPermissions
from policies.guard_policies import InGuardPolicy, PreGuardPolicy
from tools.tool_registry import ToolRegistry


@dataclass
class PreGuard:
    # Pre-Guard 不调用大模型，只做确定性的上下文装配。
    permissions: UserPermissions
    registry: ToolRegistry
    pre_policy: PreGuardPolicy
    in_policy: InGuardPolicy
    packages: PackageCatalog

    def build_context(self, user_request: str) -> dict[str, Any]:
        # 任务识别、权限加载、工具白名单和禁止动作都在这里完成。
        # 外部 Agent 收到这个 context 后，应该只围绕这些信息做规划。
        package = self.packages.match(user_request)
        task_type = package["task_type"] if package else "general_task"
        allowed_tools = self.registry.allowed_tool_names_for_permissions(
            self.permissions, package_name=package.get("name") if package else None
        )
        return {
            "task_type": task_type,
            "package_name": package.get("name") if package else None,
            "user_request": user_request,
            "user": {
                "user_id": self.permissions.user_id,
                "roles": self.permissions.roles,
                "allowed_actions": sorted(self.permissions.allowed_actions),
            },
            "business_rules": package.get("rules", {}) if package else {},
            "tool_policy": {
                "allowed_tools": allowed_tools,
                "tool_schemas": self.registry.describe(allowed_tools),
                "forbidden_actions": sorted(self.in_policy.forbidden_actions),
            },
            "model_instructions": list(
                dict.fromkeys(
                    self.pre_policy.general_model_instructions
                    + (package.get("model_instructions", []) if package else [])
                )
            ),
        }
