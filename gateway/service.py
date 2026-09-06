from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from guards.in_guard import InGuard
from guards.post_guard import PostGuard
from guards.pre_guard import PreGuard
from gateway.logging_config import append_jsonl, setup_file_logger
from policies.guard_policies import (
    load_in_guard_policy,
    load_post_guard_policy,
    load_pre_guard_policy,
)
from policies.permissions import load_user_permissions
from policies.rules import load_business_rules
from runtime.executor import ToolCall
from tools.tool_registry import build_expense_tool_registry


@dataclass
class GuardSession:
    # 一个 session 对应外部平台里的一次用户任务。
    # 后续每次工具调用和结果复核都靠 session_id 找回事前装配的上下文。
    session_id: str
    user_id: str
    context: dict[str, Any]
    # observations 保存真实工具返回，Post-Guard 只认可这里的证据。
    observations: list[dict[str, Any]] = field(default_factory=list)
    # attempt_no 用来表达 Agent Loop 的第几轮。
    attempt_no: int = 1
    # 新一轮开始后，Post-Guard 只检查本轮新增的工具拦截记录。
    attempt_call_log_start: int = 0


class GuardGatewayService:
    """外部 Agent 平台接入时使用的三阶段网关服务。"""

    def __init__(self, base_dir: Path | None = None, policy_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(__file__).resolve().parent.parent
        # 所有可变规则都集中放在 config/policies，方便业务方直接改 JSON。
        self.policy_dir = policy_dir or self.base_dir / "config" / "policies"
        self.data_path = self.base_dir / "data" / "sample_expense.json"
        self.rules = load_business_rules(self.policy_dir)
        self.pre_guard_policy = load_pre_guard_policy(self.policy_dir)
        self.in_guard_policy = load_in_guard_policy(self.policy_dir)
        self.post_guard_policy = load_post_guard_policy(self.policy_dir)
        self.registry = build_expense_tool_registry(data_path=self.data_path, rules=self.rules)
        self.sessions: dict[str, GuardSession] = {}
        self.in_guards: dict[str, InGuard] = {}
        self.logger = setup_file_logger(self.base_dir)
        self.logger.info("GuardGatewayService 已启动，policy_dir=%s", self.policy_dir)

    def build_context(self, user_id: str, user_request: str) -> dict[str, Any]:
        # Pre-Guard：在外部 Agent 开始规划前，先生成它能看到的业务规则、权限和工具白名单。
        permissions = load_user_permissions(user_id=user_id, policy_dir=self.policy_dir)
        user_id = permissions.user_id
        in_guard = InGuard(
            rules=self.rules,
            permissions=permissions,
            registry=self.registry,
            policy=self.in_guard_policy,
        )
        pre_guard = PreGuard(
            rules=self.rules,
            permissions=permissions,
            registry=self.registry,
            pre_policy=self.pre_guard_policy,
            in_policy=self.in_guard_policy,
        )
        context = pre_guard.build_context(user_request)
        session_id = str(uuid4())

        self.sessions[session_id] = GuardSession(
            session_id=session_id,
            user_id=user_id,
            context=context,
            attempt_call_log_start=0,
        )
        self.in_guards[session_id] = in_guard
        self.logger.info(
            "Pre-Guard context_build session_id=%s user_id=%s allowed_tools=%s",
            session_id,
            user_id,
            context["tool_policy"]["allowed_tools"],
        )
        append_jsonl(
            self.base_dir,
            "audit.jsonl",
            {
                "event": "context_build",
                "session_id": session_id,
                "user_id": user_id,
                "allowed_tools": context["tool_policy"]["allowed_tools"],
                "forbidden_actions": context["tool_policy"]["forbidden_actions"],
            },
        )

        return {
            "session_id": session_id,
            "context": context,
            # 对 QwenPaw / DeerFlow 这类外部平台来说，重点是保存 session_id。
            "integration_note": "外部平台后续业务工具调用必须携带 session_id 走 /tools/call。",
        }

    def audit_expense(
        self,
        user_request: str,
        user_id: str = "auditor_001",
        expense_id: str | None = None,
        project: str = "project_a",
    ) -> dict[str, Any]:
        # 一体化入口：外部 Agent 不想自己编排多步流程时，直接调用这个工具即可。
        # 内部仍然完整经过 Pre-Guard -> In-Guard -> Tool -> Post-Guard。
        context_response = self.build_context(user_id=user_id, user_request=user_request)
        session_id = context_response["session_id"]

        # Demo 默认选择第一张报销单；真实系统可把 expense_id 从用户输入或业务系统中传进来。
        listed = self.call_tool(session_id, "list_expense_forms", {})
        selected_expense_id = expense_id or self._select_first_expense_id(listed)
        read_result = self.call_tool(
            session_id,
            "read_expense_form",
            {"expense_id": selected_expense_id},
        )
        invoice_result = self.call_tool(
            session_id,
            "check_invoice",
            {"expense_id": selected_expense_id},
        )
        calculation_result = self.call_tool(
            session_id,
            "calculate_reimbursement",
            {"expense_id": selected_expense_id, "project": project},
        )

        if not calculation_result["allowed"]:
            # 工具调用被事中拦截时，不再生成看似成功的审核结论。
            return self._blocked_auto_audit(
                session_id=session_id,
                context_response=context_response,
                tool_results=[listed, read_result, invoice_result, calculation_result],
                reason=calculation_result["reason"],
            )

        opinion_result = self.call_tool(
            session_id,
            "generate_audit_opinion",
            {
                "expense_id": selected_expense_id,
                "calculation": calculation_result["result"],
                "include_payment_commitment": False,
            },
        )

        if not opinion_result["allowed"]:
            # 比如 Agent/调用方要求生成“已付款”承诺，这里会被硬拦截。
            return self._blocked_auto_audit(
                session_id=session_id,
                context_response=context_response,
                tool_results=[
                    listed,
                    read_result,
                    invoice_result,
                    calculation_result,
                    opinion_result,
                ],
                reason=opinion_result["reason"],
            )

        calculation = calculation_result["result"]
        # 最终输出必须携带 source_tools，Post-Guard 会检查它是否真的来自工具结果。
        final_answer = {
            "status": "passed",
            "message": opinion_result["result"]["opinion"],
            "project_a_reimbursable": calculation["project_a_reimbursable"],
            "other_channel_amount": calculation["other_channel_amount"],
            "not_allowed_in_project_a": calculation["not_allowed_in_project_a"],
            "exceptions": calculation["exceptions"],
            "source_tools": [
                "list_expense_forms",
                "read_expense_form",
                "check_invoice",
                "calculate_reimbursement",
                "generate_audit_opinion",
            ],
            "forbidden_commitments": [],
        }
        review = self.review_output(session_id=session_id, final_answer=final_answer)

        return {
            "status": "success" if review["passed"] else "review_failed",
            "session_id": session_id,
            "context": context_response["context"],
            "selected_expense_id": selected_expense_id,
            "tool_results": [
                listed,
                read_result,
                invoice_result,
                calculation_result,
                opinion_result,
            ],
            "review": review,
            "final_answer": final_answer if review["passed"] else None,
        }

    def call_tool(
        self, session_id: str, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        # In-Guard：所有业务工具统一走这里，先校验白名单、权限、禁用动作和参数 Schema。
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
        # 日志分两类：普通 log 方便看运行状态，audit.jsonl 方便机器审计和追踪。
        self.logger.info(
            "In-Guard tool_call session_id=%s tool=%s allowed=%s reason=%s",
            session_id,
            result.tool,
            result.allowed,
            result.reason,
        )
        append_jsonl(
            self.base_dir,
            "audit.jsonl",
            {
                "event": "tool_call",
                "session_id": session_id,
                "attempt_no": session.attempt_no,
                "tool": result.tool,
                "arguments": arguments,
                "allowed": result.allowed,
                "reason": result.reason,
            },
        )
        return observation

    def start_attempt(self, session_id: str) -> dict[str, Any]:
        session = self._get_session(session_id)
        # 外部 Agent 的下一轮重试必须先调用这个接口，避免上一轮被拦截记录污染本轮复核。
        session.attempt_no += 1
        session.attempt_call_log_start = len(self.in_guards[session_id].call_log)
        self.logger.info(
            "Agent Loop attempt_start session_id=%s attempt_no=%s",
            session_id,
            session.attempt_no,
        )
        append_jsonl(
            self.base_dir,
            "audit.jsonl",
            {
                "event": "attempt_start",
                "session_id": session_id,
                "attempt_no": session.attempt_no,
            },
        )
        return {
            "session_id": session_id,
            "attempt_no": session.attempt_no,
            "message": "已开启新的复核轮次，后续 Post-Guard 只复核本轮新增工具调用。",
        }

    def review_output(self, session_id: str, final_answer: dict[str, Any]) -> dict[str, Any]:
        # Post-Guard：在外部 Agent 准备回复用户前，检查输出是否可信、合规、可追溯。
        session = self._get_session(session_id)
        permissions = load_user_permissions(user_id=session.user_id, policy_dir=self.policy_dir)
        post_guard = PostGuard(
            rules=self.rules,
            permissions=permissions,
            policy=self.post_guard_policy,
        )
        in_guard = self.in_guards[session_id]
        review = post_guard.review(
            final_answer=final_answer,
            observations=session.observations,
            # 只把当前轮次的工具调用日志交给复核器，支持 Agent Loop 多轮重试。
            call_log=in_guard.call_log[session.attempt_call_log_start :],
        )
        response = {
            "attempt_no": session.attempt_no,
            "passed": review.passed,
            "reasons": review.reasons,
            "action": "allow_output" if review.passed else "retry_or_human_confirm",
            "message": "复核通过，可以输出给用户。" if review.passed else "复核失败，请按原因重试或转人工。",
        }
        self.logger.info(
            "Post-Guard output_review session_id=%s attempt_no=%s passed=%s reasons=%s",
            session_id,
            session.attempt_no,
            review.passed,
            review.reasons,
        )
        append_jsonl(
            self.base_dir,
            "audit.jsonl",
            {
                "event": "output_review",
                "session_id": session_id,
                "attempt_no": session.attempt_no,
                "passed": review.passed,
                "reasons": review.reasons,
            },
        )
        return response

    def audit_logs(self, session_id: str | None = None) -> dict[str, Any]:
        # 返回内存中的工具调用日志；持久化审计日志在 logs/audit.jsonl。
        if session_id:
            self._get_session(session_id)
            return {"session_id": session_id, "logs": self.in_guards[session_id].call_log}

        return {
            "sessions": {
                item: self.in_guards[item].call_log for item in sorted(self.sessions)
            }
        }

    def reload_policy(self) -> dict[str, Any]:
        # 策略热重载：业务规则改完 JSON 后调用它即可生效。
        # 为避免旧上下文继续使用旧规则，重载后清空已有 session。
        self.rules = load_business_rules(self.policy_dir)
        self.pre_guard_policy = load_pre_guard_policy(self.policy_dir)
        self.in_guard_policy = load_in_guard_policy(self.policy_dir)
        self.post_guard_policy = load_post_guard_policy(self.policy_dir)
        self.registry = build_expense_tool_registry(data_path=self.data_path, rules=self.rules)
        self.sessions.clear()
        self.in_guards.clear()
        self.logger.info("策略已重新加载，policy_dir=%s", self.policy_dir)
        append_jsonl(
            self.base_dir,
            "audit.jsonl",
            {
                "event": "policy_reload",
                "policy_dir": str(self.policy_dir),
            },
        )
        return {
            "reloaded": True,
            "policy_dir": str(self.policy_dir),
            "note": "策略已重新加载，已有 session 已清空。",
        }

    def _get_session(self, session_id: str) -> GuardSession:
        session = self.sessions.get(session_id)
        if session is None:
            raise KeyError(f"session_id 不存在：{session_id}")
        return session

    @staticmethod
    def _select_first_expense_id(list_result: dict[str, Any]) -> str:
        # Demo 简化：没有指定报销单时选择列表第一项。
        if not list_result["allowed"]:
            raise ValueError(f"无法列出报销单：{list_result['reason']}")
        items = list_result["result"].get("items", [])
        if not items:
            raise ValueError("没有可审核的报销单。")
        return items[0]["expense_id"]

    @staticmethod
    def _blocked_auto_audit(
        session_id: str,
        context_response: dict[str, Any],
        tool_results: list[dict[str, Any]],
        reason: str | None,
    ) -> dict[str, Any]:
        # 统一返回“自动审核被阻断”的结构，调用方可以据此转人工或重新授权。
        return {
            "status": "blocked",
            "session_id": session_id,
            "context": context_response["context"],
            "tool_results": tool_results,
            "review": {
                "passed": False,
                "reasons": [reason or "自动审核被工具拦截。"],
                "action": "human_confirm",
            },
            "final_answer": None,
        }
