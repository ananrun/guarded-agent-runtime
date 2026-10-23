from __future__ import annotations

import re
from typing import Any


class RuleEngine:
    """执行业务包声明的公式与规则；不使用 eval，也不包含业务判断。"""

    def __init__(self, rule_sets: dict[str, Any]) -> None:
        self.rule_sets = rule_sets

    def evaluate(self, rule_set_name: str, record: dict[str, Any]) -> dict[str, Any]:
        rule_set = self.rule_sets.get(rule_set_name)
        if not isinstance(rule_set, dict):
            raise ValueError(f"未找到规则集：{rule_set_name}")

        values: dict[str, Any] = {"record": record, "derived": {}}
        for name, expression in rule_set.get("derive", {}).items():
            values["derived"][name] = self._expression(expression, values)

        matched: list[str] = []
        for rule in rule_set.get("rules", []):
            if self._condition(rule.get("when", {}), values):
                matched.append(rule["id"])
                result = self._resolve(rule.get("result", {}), values)
                return {
                    "completed": True,
                    "rule_set": rule_set_name,
                    "derived": values["derived"],
                    "matched_rules": matched,
                    **result,
                }

        fallback = rule_set.get("default")
        if fallback is None:
            raise ValueError(f"规则集 {rule_set_name} 未命中任何规则，且未配置 default")
        return {
            "completed": True,
            "rule_set": rule_set_name,
            "derived": values["derived"],
            "matched_rules": matched,
            **self._resolve(fallback, values),
        }

    def _expression(self, expression: Any, values: dict[str, Any]) -> Any:
        if not isinstance(expression, dict) or "op" not in expression:
            return self._resolve(expression, values)
        op = expression["op"]
        left = self._expression(expression.get("left"), values)
        right = self._expression(expression.get("right"), values)
        if op == "add":
            value = left + right
        elif op == "subtract":
            value = left - right
        elif op == "multiply":
            value = left * right
        elif op == "divide":
            if right == 0:
                raise ValueError("规则计算除数不能为 0")
            value = left / right
        else:
            raise ValueError(f"不支持的公式操作：{op}")
        return round(value, int(expression["round"])) if "round" in expression else value

    def _condition(self, condition: dict[str, Any], values: dict[str, Any]) -> bool:
        if "all" in condition:
            return all(self._condition(item, values) for item in condition["all"])
        if "any" in condition:
            return any(self._condition(item, values) for item in condition["any"])
        left = self._resolve(condition.get("left"), values)
        right = self._resolve(condition.get("right"), values)
        op = condition.get("op", "eq")
        comparisons = {
            "eq": lambda: left == right,
            "ne": lambda: left != right,
            "gt": lambda: left > right,
            "gte": lambda: left >= right,
            "lt": lambda: left < right,
            "lte": lambda: left <= right,
            "in": lambda: left in right,
        }
        if op not in comparisons:
            raise ValueError(f"不支持的条件操作：{op}")
        return comparisons[op]()

    def _resolve(self, value: Any, values: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {key: self._resolve(item, values) for key, item in value.items()}
        if isinstance(value, list):
            return [self._resolve(item, values) for item in value]
        if isinstance(value, str) and value.startswith("$"):
            return self._path(value[1:], values)
        return value

    @staticmethod
    def _path(path: str, values: dict[str, Any]) -> Any:
        current: Any = values
        for name, index in re.findall(r"([^.\[\]]+)|\[(\d+)\]", path):
            key: str | int = int(index) if index else name
            try:
                current = current[key]
            except (KeyError, IndexError, TypeError) as exc:
                raise ValueError(f"规则引用不存在：${path}") from exc
        return current
