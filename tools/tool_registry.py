from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from policies.permissions import UserPermissions
from policies.rules import BusinessRules
from tools.expense_tools import ExpenseTools


@dataclass(frozen=True)
class ToolSpec:
    # 工具注册表中的最小元数据：名称、函数、所需权限和参数 Schema。
    name: str
    func: Callable[..., Any]
    required_permission: str
    schema: dict[str, type]

    def validate_arguments(self, arguments: dict[str, Any]) -> str | None:
        # 这里做轻量 Schema 校验，先覆盖 Demo 必需的缺参、类型和额外参数检查。
        for field, expected_type in self.schema.items():
            if field not in arguments:
                return f"缺少参数 {field}"
            if not isinstance(arguments[field], expected_type):
                return f"参数 {field} 应为 {expected_type.__name__}"
        extra = set(arguments) - set(self.schema)
        if extra:
            return f"包含未声明参数 {', '.join(sorted(extra))}"
        return None


class ToolRegistry:
    def __init__(self, tools: list[ToolSpec]) -> None:
        # 注册表是 In-Guard 的唯一工具来源，未注册工具一律不能执行。
        self._tools = {tool.name: tool for tool in tools}

    def get(self, name: str) -> ToolSpec:
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def allowed_tool_names_for_permissions(self, permissions: UserPermissions) -> list[str]:
        # Pre-Guard 用它把用户权限转换成当前上下文的工具白名单。
        return [
            tool.name
            for tool in self._tools.values()
            if tool.required_permission in permissions.allowed_actions
        ]


def build_expense_tool_registry(data_path: Path, rules: BusinessRules) -> ToolRegistry:
    # 业务工具集中在这里注册；新增工具时必须声明 required_permission 和 schema。
    expense_tools = ExpenseTools(data_path=data_path, rules=rules)
    return ToolRegistry(
        [
            ToolSpec(
                name="list_expense_forms",
                func=expense_tools.list_expense_forms,
                required_permission="expense:list",
                schema={},
            ),
            ToolSpec(
                name="read_expense_form",
                func=expense_tools.read_expense_form,
                required_permission="expense:read",
                schema={"expense_id": str},
            ),
            ToolSpec(
                name="check_invoice",
                func=expense_tools.check_invoice,
                required_permission="invoice:check",
                schema={"expense_id": str},
            ),
            ToolSpec(
                name="calculate_reimbursement",
                func=expense_tools.calculate_reimbursement,
                required_permission="reimbursement:calculate",
                schema={"expense_id": str, "project": str},
            ),
            ToolSpec(
                name="generate_audit_opinion",
                func=expense_tools.generate_audit_opinion,
                required_permission="audit_opinion:generate",
                schema={"expense_id": str, "calculation": dict, "include_payment_commitment": bool},
            ),
        ]
    )
