from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tools.rule_engine import RuleEngine


class ConfiguredProvider:
    """由 JSON 工具包驱动的数据适配器，不包含任何领域规则。"""

    def __init__(self, package_dir: Path, pack: dict[str, Any]) -> None:
        self.pack = pack
        data_file = pack.get("data_file")
        self.package_dir = package_dir.resolve()
        self.data = self._load_data_file(data_file) if data_file else {}
        rule_file = pack.get("rule_file")
        self.rule_engine = RuleEngine(self._load(self._package_file(rule_file)).get("rule_sets", {})) if rule_file else None

    def execute(self, operation: dict[str, Any], arguments: dict[str, Any]) -> Any:
        kind = operation["kind"]
        source = self._path(self.data, operation.get("source", ""))
        if kind == "list":
            rows = source if isinstance(source, list) else []
            fields = operation.get("fields")
            return {
                operation.get("result_key", "items"): [
                    {field: row.get(field) for field in fields} if fields else row
                    for row in rows
                ]
            }
        if kind == "find":
            for row in source or []:
                if row.get(operation["match_argument"]) == arguments.get(operation["match_argument"]):
                    return row
            raise ValueError(f"未找到匹配记录：{arguments.get(operation['match_argument'])}")
        if kind == "lookup":
            key = self._render(operation["key"], arguments)
            value = source.get(key) if isinstance(source, dict) else None
            if value is None:
                raise ValueError(f"未找到配置结果：{key}")
            return value
        if kind == "rule_evaluate":
            if self.rule_engine is None:
                raise ValueError("工具包未声明 rule_file，不能执行规则计算")
            record = self._find(source, operation["match_argument"], arguments)
            return self.rule_engine.evaluate(operation["rule_set"], record)
        raise ValueError(f"不支持的配置工具操作：{kind}")

    def _find(self, source: Any, match_argument: str, arguments: dict[str, Any]) -> dict[str, Any]:
        for row in source or []:
            if row.get(match_argument) == arguments.get(match_argument):
                return row
        raise ValueError(f"未找到匹配记录：{arguments.get(match_argument)}")

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _load_data_file(self, data_file: str) -> dict[str, Any]:
        path = self._package_file(data_file)
        return self._load(path)

    def _package_file(self, filename: str) -> Path:
        path = (self.package_dir / filename).resolve()
        try:
            path.relative_to(self.package_dir)
        except ValueError as exc:
            raise ValueError("配置文件必须位于业务包目录内。") from exc
        return path

    @staticmethod
    def _path(data: Any, path: str) -> Any:
        current = data
        for key in filter(None, path.split(".")):
            current = current[key]
        return current

    @staticmethod
    def _render(template: str, arguments: dict[str, Any]) -> str:
        return re.sub(r"\{([^}]+)\}", lambda match: str(arguments.get(match.group(1), "")), template)


def create_provider(runtime_context: dict[str, Any]) -> ConfiguredProvider:
    return ConfiguredProvider(
        package_dir=Path(runtime_context["package_dir"]),
        pack=runtime_context["tool_pack"],
    )
