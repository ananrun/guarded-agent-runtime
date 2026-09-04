from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from policies.permissions import UserPermissions
from policies.rules import BusinessRules
from tools.expense_tools import ExpenseTools


@dataclass(frozen=True)
class ToolSpec:
    name: str
    func: Callable[..., Any]
    required_permission: str
    schema: dict[str, type]

    def validate_arguments(self, arguments: dict[str, Any]) -> str | None:
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
        self._tools = {tool.name: tool for tool in tools}

    def get(self, name: str) -> ToolSpec:
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def allowed_tool_names_for_permissions(self, permissions: UserPermissions) -> list[str]:
        return [
            tool.name
            for tool in self._tools.values()
            if tool.required_permission in permissions.allowed_actions
        ]


def build_expense_tool_registry(data_path: Path, rules: BusinessRules) -> ToolRegistry:
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
