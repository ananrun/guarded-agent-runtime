from __future__ import annotations

from dataclasses import dataclass, field
import json
from importlib import import_module
from pathlib import Path
from typing import Any, Callable

from policies.permissions import UserPermissions


@dataclass(frozen=True)
class ToolSpec:
    # 工具注册表中的最小元数据：名称、函数、所需权限和参数 Schema。
    name: str
    func: Callable[..., Any]
    required_permission: str
    schema: dict[str, type]
    optional_fields: set[str] = field(default_factory=set)
    package_name: str | None = None

    def validate_arguments(self, arguments: dict[str, Any]) -> str | None:
        # 这里做轻量 Schema 校验，先覆盖 Demo 必需的缺参、类型和额外参数检查。
        for field, expected_type in self.schema.items():
            if field not in arguments and field not in self.optional_fields:
                return f"缺少参数 {field}；允许参数：{', '.join(self.schema)}"
            if field not in arguments:
                continue
            if not isinstance(arguments[field], expected_type):
                return f"参数 {field} 应为 {expected_type.__name__}"
        extra = set(arguments) - set(self.schema)
        if extra:
            return (
                f"包含未声明参数 {', '.join(sorted(extra))}；"
                f"允许参数：{', '.join(self.schema)}"
            )
        return None


class ToolRegistry:
    def __init__(self, tools: list[ToolSpec]) -> None:
        # 注册表是 In-Guard 的唯一工具来源，未注册工具一律不能执行。
        self._tools: dict[str, ToolSpec] = {}
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> ToolSpec:
        return self._tools[name]

    def register(self, tool: ToolSpec) -> None:
        """注册业务工具；所有工具仍会经过 In-Guard 后才可执行。"""
        if tool.name in self._tools:
            raise ValueError(f"工具名称重复或已注册：{tool.name}")
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return sorted(self._tools)

    def allowed_tool_names_for_permissions(
        self, permissions: UserPermissions, package_name: str | None = None
    ) -> list[str]:
        # Pre-Guard 用它把用户权限转换成当前上下文的工具白名单。
        return [
            tool.name
            for tool in self._tools.values()
            if (tool.required_permission in permissions.allowed_actions or "*" in permissions.allowed_actions)
            and (package_name is None or tool.package_name == package_name)
        ]

    def describe(self, names: list[str]) -> dict[str, dict[str, Any]]:
        """向外部 Agent 提供参数契约，避免靠猜测拼装调用参数。"""
        return {
            name: {
                "required_permission": self._tools[name].required_permission,
                "required_arguments": [
                    field
                    for field in self._tools[name].schema
                    if field not in self._tools[name].optional_fields
                ],
                "optional_arguments": sorted(self._tools[name].optional_fields),
                "argument_types": {
                    field: type_.__name__
                    for field, type_ in self._tools[name].schema.items()
                },
            }
            for name in names
        }


def build_tool_registry(
    tool_config_dir: Path, runtime_context: dict[str, Any]
) -> ToolRegistry:
    """从工具包配置加载工具；提供者由每个配置包自行声明。"""
    types = {"str": str, "bool": bool, "dict": dict, "int": int, "float": float}
    specs: list[ToolSpec] = []
    for path in sorted(tool_config_dir.rglob("tools.json")):
        with path.open("r", encoding="utf-8") as fh:
            pack = json.load(fh)
        manifest_path = path.parent / "package.json"
        with manifest_path.open("r", encoding="utf-8") as fh:
            package_name = json.load(fh)["name"]
        provider_factory = pack.get("provider_factory")
        provider = (
            _import_callable(provider_factory)(
                {**runtime_context, "tool_pack": pack, "package_dir": path.parent}
            )
            if provider_factory
            else None
        )
        for item in pack["tools"]:
            schema = {key: types[value] for key, value in item.get("schema", {}).items()}
            if "callable" not in item and provider is None:
                raise ValueError(
                    f"工具 {item['name']} 缺少 callable，工具包也未声明 provider_factory：{path.name}"
                )
            if "callable" in item:
                func = _import_callable(item["callable"])
            elif "operation" in item:
                func = _configured_operation(provider, item["operation"])
            else:
                func = getattr(provider, item["handler"])
            specs.append(
                ToolSpec(
                    name=item["name"],
                    func=func,
                    required_permission=item["required_permission"],
                    schema=schema,
                    optional_fields=set(item.get("optional", [])),
                    package_name=package_name,
                )
            )
    return ToolRegistry(specs)


def _import_callable(reference: str) -> Callable[..., Any]:
    module_name, function_name = reference.rsplit(":", 1)
    return getattr(import_module(module_name), function_name)


def _configured_operation(provider: Any, operation: dict[str, Any]) -> Callable[..., Any]:
    return lambda **arguments: provider.execute(operation, arguments)
