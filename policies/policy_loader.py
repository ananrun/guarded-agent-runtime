from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def default_policy_dir() -> Path:
    # 默认策略目录，所有三阶段规则都从这里读取。
    return Path(__file__).resolve().parent.parent / "config" / "policies"


def load_json_config(name: str, policy_dir: Path | None = None) -> dict[str, Any]:
    # 单文件加载函数，便于各模块只关心自己需要的策略文件。
    path = (policy_dir or default_policy_dir()) / name
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_policy_document(policy_dir: Path | None = None) -> dict[str, Any]:
    # 调试或管理界面需要一次性查看全部策略时使用。
    return {
        "users": load_json_config("users.json", policy_dir),
        "business_rules": load_json_config("business_rules.json", policy_dir),
        "pre_guard": load_json_config("pre_guard.json", policy_dir),
        "in_guard": load_json_config("in_guard.json", policy_dir),
        "post_guard": load_json_config("post_guard.json", policy_dir),
    }
