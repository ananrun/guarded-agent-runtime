from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UserPermissions:
    user_id: str
    roles: list[str]
    allowed_actions: set[str]


def load_user_permissions(user_id: str) -> UserPermissions:
    return UserPermissions(
        user_id=user_id,
        roles=["expense_auditor"],
        allowed_actions={
            "expense:read",
            "invoice:check",
            "reimbursement:calculate",
            "audit_opinion:generate",
        },
    )
