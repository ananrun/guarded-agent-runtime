from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from policies.policy_loader import load_policy_document


@dataclass(frozen=True)
class UserPermissions:
    user_id: str
    roles: list[str]
    allowed_actions: set[str]


def load_user_permissions(user_id: str, policy_path: Path | None = None) -> UserPermissions:
    policy = load_policy_document(policy_path)
    user_policy = policy["users"].get(user_id)
    if user_policy is None:
        return UserPermissions(user_id=user_id, roles=[], allowed_actions=set())

    return UserPermissions(
        user_id=user_id,
        roles=user_policy["roles"],
        allowed_actions=set(user_policy["allowed_actions"]),
    )
