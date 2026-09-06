from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any


class Sandbox:
    """确定性工具的最小沙箱边界。

    当前原型通过深拷贝隔离工具入参，并统一收口工具执行入口。
    生产环境可替换为进程、容器、网络、文件系统或能力级隔离。
    """

    def run(self, func: Callable[..., Any], arguments: dict[str, Any]) -> Any:
        # 深拷贝入参，避免工具内部意外修改外部 Agent 传入的原始对象。
        safe_arguments = deepcopy(arguments)
        return func(**safe_arguments)
