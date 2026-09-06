from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from policies.policy_loader import load_json_config


@dataclass(frozen=True)
class PreGuardPolicy:
    # 事前规则：任务识别关键词，以及注入给外部 Agent 的模型约束。
    task_keywords: dict[str, list[str]]
    model_instructions: list[str]


@dataclass(frozen=True)
class InGuardPolicy:
    # 事中规则：决定哪些硬校验必须开启。
    forbidden_actions: set[str]
    enforce_tool_whitelist: bool
    enforce_registered_tools: bool
    enforce_user_permissions: bool
    enforce_schema_validation: bool


@dataclass(frozen=True)
class PostGuardPolicy:
    # 事后规则：决定最终输出需要哪些证据、字段，以及哪些承诺不能出现。
    block_on_intercepted_tool_call: bool
    required_source_tools: list[str]
    required_output_fields: list[str]
    forbidden_output_phrases: list[str]


def load_pre_guard_policy(policy_dir: Path | None = None) -> PreGuardPolicy:
    # 从独立 JSON 加载，业务方修改配置后可通过 guarded_policy_reload 生效。
    data = load_json_config("pre_guard.json", policy_dir)
    return PreGuardPolicy(
        task_keywords=data["task_keywords"],
        model_instructions=data["model_instructions"],
    )


def load_in_guard_policy(policy_dir: Path | None = None) -> InGuardPolicy:
    # 禁止动作、白名单、权限、Schema 校验开关都在 in_guard.json 中维护。
    data = load_json_config("in_guard.json", policy_dir)
    return InGuardPolicy(
        forbidden_actions=set(data["forbidden_actions"]),
        enforce_tool_whitelist=bool(data["enforce_tool_whitelist"]),
        enforce_registered_tools=bool(data["enforce_registered_tools"]),
        enforce_user_permissions=bool(data["enforce_user_permissions"]),
        enforce_schema_validation=bool(data["enforce_schema_validation"]),
    )


def load_post_guard_policy(policy_dir: Path | None = None) -> PostGuardPolicy:
    # 输出格式和越权话术检查集中在 post_guard.json。
    data = load_json_config("post_guard.json", policy_dir)
    return PostGuardPolicy(
        block_on_intercepted_tool_call=bool(data["block_on_intercepted_tool_call"]),
        required_source_tools=data["required_source_tools"],
        required_output_fields=data["required_output_fields"],
        forbidden_output_phrases=data["forbidden_output_phrases"],
    )
