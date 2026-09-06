from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    # 外部 Agent 请求执行的工具调用。
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    # In-Guard 统一返回的结果；allowed=False 表示工具没有被真正执行。
    tool: str
    allowed: bool
    result: Any
    reason: str | None
