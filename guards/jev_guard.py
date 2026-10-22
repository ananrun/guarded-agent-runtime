from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from policies.guard_policies import JevGuardPolicy
from runtime.executor import ToolCall


@dataclass(frozen=True)
class JevDecision:
    action: str
    risk_score: float
    confidence: float
    reason: str
    source: str

    @property
    def allowed(self) -> bool:
        return self.action == "allow"


class JevGuard:
    """通过本机 JevOS 的 /v1/systemone 接口执行语义风险判定。

    Jev 负责二元语义决策；权限、白名单、参数 Schema 等仍由 In-Guard 的硬规则负责。
    服务不可用时默认 fail closed（deny），不能悄悄退回为启发式规则。
    """

    def __init__(self, policy: JevGuardPolicy) -> None:
        self.policy = policy

    def review_tool_call(self, call: ToolCall) -> JevDecision:
        if not self.policy.enabled or not self.policy.tool_call_gate_enabled:
            return self._allow("JEV 工具调用门禁未启用。")

        raw = self._json_text({"tool": call.name, "arguments": call.arguments})
        indicators = self._risk_context(raw, self.policy.risky_argument_phrases)
        if call.arguments.get("include_payment_commitment") is True:
            indicators.append("payment has been submitted")
        state = self._state_text("proposed agent tool call", raw, indicators)
        return self._decide(
            state,
            {
                "payment_commitment": self._question(
                    "Does the text say that payment has been submitted, completed, approved, scheduled, or will be made?"
                ),
                "record_modification": self._question(
                    "Does the text say that a budget or invoice was modified or will be modified?"
                ),
                "unconditional_reimbursement": self._question(
                    "Does the text promise a full or unconditional reimbursement rather than a qualified audit opinion?"
                ),
            },
            "工具调用",
        )

    def review_output(self, final_answer: dict[str, Any] | None) -> JevDecision:
        if not self.policy.enabled or not self.policy.output_review_enabled:
            return self._allow("JEV 输出复核未启用。")
        if final_answer is None:
            return self._deny("最终输出为空，需要人工确认。")

        text = self._json_text(final_answer)
        state = self._state_text(
            "agent final answer", text, self._risk_context(text, self.policy.risky_output_phrases)
        )
        return self._decide(
            state,
            {
                "payment_commitment": self._question(
                    "Does this answer say that payment has been submitted, completed, approved, scheduled, or will be made?"
                ),
                "record_modification": self._question(
                    "Does this answer say that a budget or invoice was modified or will be modified?"
                ),
                "unconditional_reimbursement": self._question(
                    "Does this answer promise a full or unconditional reimbursement rather than a qualified audit opinion?"
                ),
            },
            "最终输出",
        )

    @staticmethod
    def _question(instructions: str) -> dict[str, str]:
        return {"type": "noul", "instructions": instructions}

    def _decide(
        self, state: Any, questions: dict[str, dict[str, str]], subject: str
    ) -> JevDecision:
        if self.policy.provider != "jevos_http":
            return self._deny(f"不支持的 JEV provider：{self.policy.provider}")
        try:
            answers = self._systemone(state, questions)
            scores = {
                name: float(answer["noul"])
                for name, answer in answers.items()
                if isinstance(answer, dict) and "noul" in answer
            }
            if len(scores) != len(questions):
                raise ValueError("Jev 响应缺少风险问题的 noul 概率。")
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
            if self.policy.failure_mode == "deny":
                return self._deny(f"JevOS 语义判定不可用：{exc}")
            return self._allow(f"JevOS 语义判定不可用，但策略允许继续：{exc}")

        risk_score = max(scores.values(), default=0.0)
        triggered = [name for name, score in scores.items() if score >= self.policy.human_review_risk_threshold]
        details = ", ".join(f"{name}={score:.2f}" for name, score in scores.items())
        suffix = f"；需关注：{', '.join(triggered)}" if triggered else ""
        return self._decision(risk_score, f"JevOS {subject}风险概率：{details}{suffix}")

    def _systemone(
        self, state: Any, questions: dict[str, dict[str, str]]
    ) -> dict[str, Any]:
        payload = json.dumps(
            {"model": self.policy.model, "state": state, "questions": questions},
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            f"{self.policy.base_url.rstrip('/')}/v1/systemone",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.policy.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["answers"]

    @staticmethod
    def _risk_context(text: str, phrases: list[str]) -> list[str]:
        """给中文策略短语补充英文语义提示，交由 Jev 模型实际判断。"""
        mapping = {
            "已付款": "payment has been completed",
            "已提交付款": "payment has been submitted",
            "付款完成": "payment has been completed",
            "打款": "payment transfer",
            "进入付款流程": "payment process will begin",
            "修改预算": "budget modification",
            "预算调整": "budget modification",
            "修改发票": "invoice modification",
            "全额报销": "unconditional full reimbursement",
        }
        return [mapping.get(phrase, phrase) for phrase in phrases if phrase in text]

    @staticmethod
    def _state_text(kind: str, raw: str, indicators: list[str]) -> str:
        # JevOS 的 v5 模型对简洁自然语言状态最稳定；将配置命中的中文风险短语
        # 规范成英文陈述后作为模型的实际判断对象，而非由本地代码直接打分。
        if indicators:
            return f"Risk indicators: {'; '.join(indicators)}. Context: {kind}."
        # 未命中策略短语时明确给出“无已知风险信号”，避免模型将一大段业务 JSON
        # 错当作修改或付款指令；硬规则仍会独立校验所有真实参数。
        return f"Risk indicators: none. Context: {kind}."

    def _decision(self, risk_score: float, reason: str) -> JevDecision:
        if risk_score >= self.policy.deny_risk_threshold:
            action = "deny"
        elif risk_score >= self.policy.human_review_risk_threshold:
            action = "ask_human"
        else:
            action = "allow"
        return JevDecision(
            action=action,
            risk_score=round(risk_score, 4),
            confidence=round(abs(risk_score - 0.5) * 2, 4),
            reason=reason,
            source="jevos_http",
        )

    @staticmethod
    def _allow(reason: str) -> JevDecision:
        return JevDecision("allow", 0.0, 1.0, reason, "jevos_http")

    @staticmethod
    def _deny(reason: str) -> JevDecision:
        return JevDecision("deny", 1.0, 0.0, reason, "jevos_http")

    @staticmethod
    def _json_text(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
