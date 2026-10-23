from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class ConfiguredProvider:
    """由 JSON 工具包驱动的数据适配器，不包含任何领域规则。"""

    def __init__(self, package_dir: Path, pack: dict[str, Any]) -> None:
        self.pack = pack
        data_file = pack.get("data_file")
        self.package_dir = package_dir.resolve()
        self.data = self._load_data_file(data_file) if data_file else {}

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
        raise ValueError(f"不支持的配置工具操作：{kind}")

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _load_data_file(self, data_file: str) -> dict[str, Any]:
        path = (self.package_dir / data_file).resolve()
        try:
            path.relative_to(self.package_dir)
        except ValueError as exc:
            raise ValueError("配置数据文件必须位于业务包目录内。") from exc
        return self._load(path)

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
