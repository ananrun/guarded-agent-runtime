from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class WorkflowDefinition:
    name: str
    task_type: str
    steps: list[dict[str, Any]]
    output: dict[str, Any]


class WorkflowEngine:
    """执行 JSON 声明的工作流，不包含任何业务领域判断。"""

    def __init__(self, workflow_dir: Path) -> None:
        self.workflow_dir = workflow_dir

    def load(self, name: str) -> WorkflowDefinition:
        data = None
        for path in self.workflow_dir.rglob("workflow.json"):
            with path.open("r", encoding="utf-8") as fh:
                candidate = json.load(fh)
            if candidate.get("name") == name:
                data = candidate
                break
        if data is None:
            raise ValueError(f"未找到工作流：{name}")
        return WorkflowDefinition(
            name=data["name"],
            task_type=data.get("task_type", "general_task"),
            steps=data["steps"],
            output=data["output"],
        )

    def run(
        self,
        workflow: WorkflowDefinition,
        inputs: dict[str, Any],
        call_tool: Callable[[str, dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        values: dict[str, Any] = {"input": dict(inputs), "steps": {}}
        tool_results: list[dict[str, Any]] = []

        for step in workflow.steps:
            kind = step.get("kind", "tool")
            if kind == "assign":
                for name, value in step["values"].items():
                    values["input"][name] = self._resolve(value, values)
                continue

            if kind == "require":
                actual = self._resolve(step["path"], values)
                if actual != step["equals"]:
                    return {
                        "blocked": True,
                        "reason": self._render(step["reason"], values),
                        "tool_results": tool_results,
                    }
                continue

            if kind != "tool":
                raise ValueError(f"工作流 {workflow.name} 包含未知步骤类型：{kind}")

            arguments = self._resolve(step.get("arguments", {}), values)
            # 未解析到的变量视为未提供，交给工具 Schema 返回统一的“缺少参数”提示。
            arguments = {key: value for key, value in arguments.items() if value is not None}
            result = call_tool(step["tool"], arguments)
            tool_results.append(result)
            if not result["allowed"]:
                return {
                    "blocked": True,
                    "reason": result["reason"] or f"工具 {step['tool']} 被拦截。",
                    "tool_results": tool_results,
                }
            values["steps"][step["id"]] = result["result"]

        return {
            "blocked": False,
            "tool_results": tool_results,
            "final_answer": self._resolve(workflow.output, values),
        }

    def _resolve(self, value: Any, values: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {key: self._resolve(item, values) for key, item in value.items()}
        if isinstance(value, list):
            return [self._resolve(item, values) for item in value]
        if isinstance(value, str) and value.startswith("$"):
            for candidate in value[1:].split(" ?? "):
                candidate = candidate.strip()
                if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in {"'", "\""}:
                    return candidate[1:-1]
                resolved = self._get_path(candidate.lstrip("$"), values)
                if resolved is not None:
                    return resolved
            return None
        return value

    def _render(self, template: str, values: dict[str, Any]) -> str:
        return re.sub(
            r"\{\{([^}]+)\}\}",
            lambda match: str(self._get_path(match.group(1).strip(), values) or "无"),
            template,
        )

    @staticmethod
    def _get_path(path: str, values: dict[str, Any]) -> Any:
        current: Any = values
        for name, index in re.findall(r"([^.\[\]]+)|\[(\d+)\]", path):
            key: str | int = int(index) if index else name
            try:
                current = current[key]
            except (KeyError, IndexError, TypeError):
                return None
        return current
