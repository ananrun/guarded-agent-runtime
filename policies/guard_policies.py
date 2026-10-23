from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from policies.policy_loader import load_json_config


@dataclass(frozen=True)
class PreGuardPolicy:
    # 事前规则：注入给外部 Agent 的通用约束。
    general_model_instructions: list[str]


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


@dataclass(frozen=True)
class JevGuardPolicy:
    # JEV 是可选的语义风险层，只做风险评分和转人工建议，不替代硬规则。
    enabled: bool
    provider: str
    tool_call_gate_enabled: bool
    output_review_enabled: bool
    human_review_risk_threshold: float
    deny_risk_threshold: float
    risky_tool_names: list[str]
    risky_argument_phrases: list[str]
    risky_output_phrases: list[str]
    risk_questions: dict[str, str]
    risk_phrase_hints: dict[str, str]
    base_url: str
    model: str
    timeout_seconds: float
    failure_mode: str


def load_pre_guard_policy(policy_dir: Path | None = None) -> PreGuardPolicy:
    # 从独立 JSON 加载，业务方修改配置后可通过 guarded_policy_reload 生效。
    data = load_json_config("pre_guard.json", policy_dir)
    return PreGuardPolicy(
        general_model_instructions=data.get(
            "general_model_instructions",
            ["只能调用工具白名单中的工具。", "不得编造工具没有返回的数据。"],
        ),
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


def load_jev_guard_policy(policy_dir: Path | None = None) -> JevGuardPolicy:
    # jev.json 可以关闭；关闭后系统退回纯确定性三阶段约束。
    data = load_json_config("jev.json", policy_dir)
    return JevGuardPolicy(
        enabled=bool(data["enabled"]),
        provider=data["provider"],
        tool_call_gate_enabled=bool(data["tool_call_gate"]["enabled"]),
        output_review_enabled=bool(data["output_review"]["enabled"]),
        human_review_risk_threshold=float(data["human_review_risk_threshold"]),
        deny_risk_threshold=float(data["deny_risk_threshold"]),
        risky_tool_names=data["risky_tool_names"],
        risky_argument_phrases=data["risky_argument_phrases"],
        risky_output_phrases=data["risky_output_phrases"],
        risk_questions=data.get("risk_questions", {}),
        risk_phrase_hints=data.get("risk_phrase_hints", {}),
        base_url=data.get("base_url", "http://127.0.0.1:8017"),
        model=data.get("model", "jev-latest"),
        timeout_seconds=float(data.get("timeout_seconds", 3.0)),
        failure_mode=data.get("failure_mode", "deny"),
    )
