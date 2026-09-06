from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from policies.rules import BusinessRules


def money(value: Decimal) -> float:
    # 金额统一保留两位小数，避免 float 直接参与财务计算。
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class ExpenseTools:
    """差旅报销 Demo 的业务工具实现。"""

    def __init__(self, data_path: Path, rules: BusinessRules) -> None:
        self.data_path = data_path
        self.rules = rules

    def list_expense_forms(self) -> dict[str, Any]:
        # QwenPaw 这类外部平台可能不知道 expense_id，先给它一个受控列表入口。
        data = self._load()
        return {
            "items": [
                {
                    "expense_id": data["expense_id"],
                    "applicant": data["applicant"],
                    "project": data["project"],
                    "currency": data["currency"],
                    "item_count": len(data["items"]),
                    "note": "Demo 环境只有这一张示例报销单。",
                }
            ]
        }

    def read_expense_form(self, expense_id: str) -> dict[str, Any]:
        # 这里只读取示例数据；真实系统可替换成数据库或报销系统 API。
        data = self._load()
        if data["expense_id"] != expense_id:
            raise ValueError(f"报销单 {expense_id} 不存在")
        return data

    def check_invoice(self, expense_id: str) -> dict[str, Any]:
        # 发票核验结果作为后续计算和复核的真实依据。
        data = self.read_expense_form(expense_id)
        seen = set()
        duplicate_items = []
        missing_receipt_items = []
        for item in data["items"]:
            invoice_no = item.get("invoice_no")
            if invoice_no in seen:
                duplicate_items.append(item["name"])
            seen.add(invoice_no)
            if not item.get("has_receipt"):
                missing_receipt_items.append(item["name"])
        return {
            "expense_id": expense_id,
            "duplicate_items": duplicate_items,
            "missing_receipt_items": missing_receipt_items,
            "passed": not duplicate_items and not missing_receipt_items,
        }

    def calculate_reimbursement(self, expense_id: str, project: str) -> dict[str, Any]:
        if project != "project_a":
            raise ValueError("Demo 当前只支持 project_a")

        data = self.read_expense_form(expense_id)
        eligible_total = Decimal("0")
        excluded_total = Decimal("0")
        not_allowed = []
        exceptions = []

        invoice_check = self.check_invoice(expense_id)
        if invoice_check["duplicate_items"]:
            exceptions.append({"type": "duplicate_invoice", "items": invoice_check["duplicate_items"]})
        if invoice_check["missing_receipt_items"]:
            exceptions.append({"type": "missing_receipt", "items": invoice_check["missing_receipt_items"]})

        for item in data["items"]:
            amount = Decimal(str(item["amount"]))
            # 保险费、餐费等排除项不能进入项目A，只能计入其他渠道或人工处理。
            if item["category"] in self.rules.excluded_from_project_a:
                excluded_total += amount
                not_allowed.append(
                    {
                        "name": item["name"],
                        "category": item["category"],
                        "amount": money(amount),
                        "reason": "业务规则禁止计入项目A",
                    }
                )
            else:
                eligible_total += amount

        # 项目A金额受项目限额控制，超限部分转入其他渠道金额。
        project_a_amount = min(eligible_total, self.rules.project_a_limit)
        over_limit = max(Decimal("0"), eligible_total - self.rules.project_a_limit)
        other_channel = excluded_total + over_limit

        return {
            "expense_id": expense_id,
            "eligible_before_limit": money(eligible_total),
            "project_a_limit": money(self.rules.project_a_limit),
            "project_a_reimbursable": money(project_a_amount),
            "over_project_a_limit": money(over_limit),
            "other_channel_amount": money(other_channel),
            "not_allowed_in_project_a": not_allowed,
            "exceptions": exceptions,
        }

    def generate_audit_opinion(
        self,
        expense_id: str,
        calculation: dict[str, Any],
        include_payment_commitment: bool = False,
    ) -> dict[str, Any]:
        if include_payment_commitment:
            raise ValueError("审核意见工具不能生成付款承诺")
        # 该工具只生成审核意见，不执行付款、改预算或改票据。
        return {
            "expense_id": expense_id,
            "opinion": (
                f"项目A可报销 {calculation['project_a_reimbursable']} 元；"
                f"其他渠道承担 {calculation['other_channel_amount']} 元；"
                "餐费、保险费不得计入项目A；本意见不执行付款。"
            ),
        }

    def _load(self) -> dict[str, Any]:
        # Demo 数据每次从文件读取，便于你直接修改 data/sample_expense.json 做测试。
        with self.data_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
