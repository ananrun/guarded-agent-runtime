from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from guards.in_guard import InGuard
from guards.post_guard import PostGuard
from guards.pre_guard import PreGuard
from policies.permissions import load_user_permissions
from policies.rules import load_business_rules
from runtime.executor import ToolCall
from tools.tool_registry import build_expense_tool_registry


@dataclass
class GuardSession:
    session_id: str
    user_id: str
    context: dict[str, Any]
    observations: list[dict[str, Any]] = field(default_factory=list)
    attempt_no: int = 1
    attempt_call_log_start: int = 0


class GuardGatewayService:
    """外部 Agent 平台接入时使用的三阶段网关服务。"""

    def __init__(self, base_dir: Path | None = None, policy_path: Path | None = None) -> None:
        self.base_dir = base_dir or Path(__file__).resolve().parent.parent
        self.policy_path = policy_path or self.base_dir / "config" / "expense_policy.json"
        self.data_path = self.base_dir / "data" / "sample_expense.json"
        self.rules = load_business_rules(self.policy_path)
        self.registry = build_expense_tool_registry(data_path=self.data_path, rules=self.rules)
        self.sessions: dict[str, GuardSession] = {}
        self.in_guards: dict[str, InGuard] = {}

    def build_context(self, user_id: str, user_request: str) -> dict[str, Any]:
        permissions = load_user_permissions(user_id=user_id, policy_path=self.policy_path)
        in_guard = InGuard(rules=self.rules, permissions=permissions, registry=self.registry)
        pre_guard = PreGuard(rules=self.rules, permissions=permissions, registry=self.registry)
        context = pre_guard.build_context(user_request)
        session_id = str(uuid4())

        self.sessions[session_id] = GuardSession(
            session_id=session_id,
            user_id=user_id,
            context=context,
            attempt_call_log_start=0,
        )
        self.in_guards[session_id] = in_guard

        return {
            "session_id": session_id,
            "context": context,
            "integration_note": "外部平台后续业务工具调用必须携带 session_id 走 /tools/call。",
        }

    def call_tool(
        self, session_id: str, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        session = self._get_session(session_id)
        in_guard = self.in_guards[session_id]
        result = in_guard.execute(
            ToolCall(name=tool_name, arguments=arguments),
            allowed_tools=session.context["tool_policy"]["allowed_tools"],
        )
        observation = {
            "tool": result.tool,
            "allowed": result.allowed,
            "result": result.result,
            "reason": result.reason,
        }
        session.observations.append(observation)
        return observation

    def start_attempt(self, session_id: str) -> dict[str, Any]:
        session = self._get_session(session_id)
        session.attempt_no += 1
        session.attempt_call_log_start = len(self.in_guards[session_id].call_log)
        return {
            "session_id": session_id,
            "attempt_no": session.attempt_no,
            "message": "已开启新的复核轮次，后续 Post-Guard 只复核本轮新增工具调用。",
        }

    def review_output(self, session_id: str, final_answer: dict[str, Any]) -> dict[str, Any]:
        session = self._get_session(session_id)
        permissions = load_user_permissions(user_id=session.user_id, policy_path=self.policy_path)
        post_guard = PostGuard(rules=self.rules, permissions=permissions)
        in_guard = self.in_guards[session_id]
        review = post_guard.review(
            final_answer=final_answer,
            observations=session.observations,
            call_log=in_guard.call_log[session.attempt_call_log_start :],
        )
        return {
            "attempt_no": session.attempt_no,
            "passed": review.passed,
            "reasons": review.reasons,
            "action": "allow_output" if review.passed else "retry_or_human_confirm",
            "message": "复核通过，可以输出给用户。" if review.passed else "复核失败，请按原因重试或转人工。",
        }

    def audit_logs(self, session_id: str | None = None) -> dict[str, Any]:
        if session_id:
            self._get_session(session_id)
            return {"session_id": session_id, "logs": self.in_guards[session_id].call_log}

        return {
            "sessions": {
                item: self.in_guards[item].call_log for item in sorted(self.sessions)
            }
        }

    def reload_policy(self) -> dict[str, Any]:
        self.rules = load_business_rules(self.policy_path)
        self.registry = build_expense_tool_registry(data_path=self.data_path, rules=self.rules)
        self.sessions.clear()
        self.in_guards.clear()
        return {
            "reloaded": True,
            "policy_path": str(self.policy_path),
            "note": "策略已重新加载，已有 session 已清空。",
        }

    def _get_session(self, session_id: str) -> GuardSession:
        session = self.sessions.get(session_id)
        if session is None:
            raise KeyError(f"session_id 不存在：{session_id}")
        return session
