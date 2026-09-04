from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from policies.rules import BusinessRules


def money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class ExpenseTools:
    def __init__(self, data_path: Path, rules: BusinessRules) -> None:
        self.data_path = data_path
        self.rules = rules

    def read_expense_form(self, expense_id: str) -> dict[str, Any]:
        data = self._load()
        if data["expense_id"] != expense_id:
            raise ValueError(f"expense_id {expense_id} not found")
        return data

    def check_invoice(self, expense_id: str) -> dict[str, Any]:
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
            raise ValueError("demo only supports project_a")

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
            raise ValueError("audit opinion tool cannot include payment commitments")
        return {
            "expense_id": expense_id,
            "opinion": (
                f"项目A可报销 {calculation['project_a_reimbursable']} 元；"
                f"其他渠道承担 {calculation['other_channel_amount']} 元；"
                "餐费、保险费不得计入项目A；本意见不执行付款。"
            ),
        }

    def _load(self) -> dict[str, Any]:
        with self.data_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
