from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class BusinessRules:
    project_a_limit: Decimal
    excluded_from_project_a: set[str]
    forbidden_actions: set[str]
    reject_duplicate_invoice: bool
    reject_missing_receipt: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["project_a_limit"] = str(self.project_a_limit)
        data["excluded_from_project_a"] = sorted(self.excluded_from_project_a)
        data["forbidden_actions"] = sorted(self.forbidden_actions)
        return data


def load_business_rules() -> BusinessRules:
    return BusinessRules(
        project_a_limit=Decimal("25000"),
        excluded_from_project_a={"meal", "insurance"},
        forbidden_actions={"approve_payment", "modify_budget", "modify_invoice"},
        reject_duplicate_invoice=True,
        reject_missing_receipt=True,
    )
