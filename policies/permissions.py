from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from policies.policy_loader import load_json_config


@dataclass(frozen=True)
class UserPermissions:
    # 用户权限只描述“这个人能做什么”，不描述具体业务计算规则。
    user_id: str
    roles: list[str]
    allowed_actions: set[str]


def load_user_permissions(user_id: str, policy_dir: Path | None = None) -> UserPermissions:
    # 支持 user_aliases，方便外部平台传来的用户 ID 映射到本地权限账号。
    policy = load_json_config("users.json", policy_dir)
    normalized_user_id = policy.get("user_aliases", {}).get(user_id, user_id)
    user_policy = policy["users"].get(normalized_user_id)
    if user_policy is None:
        # 未配置用户默认没有任何权限，避免误放行。
        return UserPermissions(user_id=normalized_user_id, roles=[], allowed_actions=set())

    return UserPermissions(
        user_id=normalized_user_id,
        roles=user_policy["roles"],
        allowed_actions=set(user_policy["allowed_actions"]),
    )
