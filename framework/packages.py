from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PackageCatalog:
    """发现业务包元数据；框架只读取通用字段，不解释业务内容。"""

    def __init__(self, package_dir: Path) -> None:
        self.items: list[dict[str, Any]] = []
        for path in sorted(package_dir.rglob("package.json")):
            with path.open(encoding="utf-8") as fh:
                item = json.load(fh)
            for key in ("name", "task_type", "keywords", "files"):
                if key not in item:
                    raise ValueError(f"业务包 {path.parent.name} 缺少字段：{key}")
            for key in ("workflow", "tools"):
                relative_path = item["files"].get(key)
                if not relative_path or not (path.parent / relative_path).is_file():
                    raise ValueError(f"业务包 {item['name']} 缺少文件：{key}")
            with (path.parent / item["files"]["workflow"]).open(encoding="utf-8") as fh:
                workflow = json.load(fh)
            if not workflow.get("name"):
                raise ValueError(f"业务包 {item['name']} 的工作流缺少 name")
            item["_workflow_name"] = workflow["name"]
            self.items.append(item)

    def match(self, request: str) -> dict[str, Any] | None:
        return next((item for item in self.items if any(word in request for word in item.get("keywords", []))), None)

    def by_task_type(self, task_type: str) -> dict[str, Any] | None:
        return next((item for item in self.items if item["task_type"] == task_type), None)
