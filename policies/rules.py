from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from policies.policy_loader import load_policy_document


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


def load_business_rules(policy_path: Path | None = None) -> BusinessRules:
    policy = load_policy_document(policy_path)
    rules = policy["business_rules"]
    return BusinessRules(
        project_a_limit=Decimal(str(rules["project_a_limit"])),
        excluded_from_project_a=set(rules["excluded_from_project_a"]),
        forbidden_actions=set(rules["forbidden_actions"]),
        reject_duplicate_invoice=bool(rules["reject_duplicate_invoice"]),
        reject_missing_receipt=bool(rules["reject_missing_receipt"]),
    )
