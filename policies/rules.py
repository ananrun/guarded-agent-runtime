from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from policies.policy_loader import load_json_config


@dataclass(frozen=True)
class BusinessRules:
    # 业务规则和权限规则分开：这里只表达报销领域本身的限制。
    project_a_limit: Decimal
    excluded_from_project_a: set[str]
    reject_duplicate_invoice: bool
    reject_missing_receipt: bool

    def to_dict(self) -> dict[str, Any]:
        # Decimal 和 set 不能直接 JSON 序列化，转成适合注入上下文的格式。
        data = asdict(self)
        data["project_a_limit"] = str(self.project_a_limit)
        data["excluded_from_project_a"] = sorted(self.excluded_from_project_a)
        return data


def load_business_rules(policy_dir: Path | None = None) -> BusinessRules:
    # 从 business_rules.json 加载，修改限额或排除费用不需要改代码。
    rules = load_json_config("business_rules.json", policy_dir)
    return BusinessRules(
        project_a_limit=Decimal(str(rules["project_a_limit"])),
        excluded_from_project_a=set(rules["excluded_from_project_a"]),
        reject_duplicate_invoice=bool(rules["reject_duplicate_invoice"]),
        reject_missing_receipt=bool(rules["reject_missing_receipt"]),
    )
