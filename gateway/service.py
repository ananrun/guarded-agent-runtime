from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from guards.in_guard import InGuard
from guards.jev_guard import JevGuard
from guards.post_guard import PostGuard
from guards.pre_guard import PreGuard
from framework.workflows import WorkflowEngine
from framework.packages import PackageCatalog
from gateway.logging_config import append_jsonl, setup_file_logger
from policies.guard_policies import (
    load_jev_guard_policy,
    load_in_guard_policy,
    load_post_guard_policy,
    load_pre_guard_policy,
)
from policies.permissions import load_user_permissions
from tools.executor import ToolCall
from tools.tool_registry import ToolSpec, build_tool_registry


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

    def __init__(
        self,
        base_dir: Path | None = None,
        policy_dir: Path | None = None,
        package_dir: Path | None = None,
    ) -> None:
        self.base_dir = base_dir or Path(__file__).resolve().parent.parent
        # 所有可变框架规则都集中放在 config，方便直接修改 JSON。
        self.policy_dir = policy_dir or self.base_dir / "config"
        self.package_dir = package_dir or self.base_dir / "packages"
        self.workflow_dir = self.package_dir
        self.tool_config_dir = self.package_dir
        self.pre_guard_policy = load_pre_guard_policy(self.policy_dir)
        self.in_guard_policy = load_in_guard_policy(self.policy_dir)
        self.post_guard_policy = load_post_guard_policy(self.policy_dir)
        self.jev_guard_policy = load_jev_guard_policy(self.policy_dir)
        self.jev_guard = JevGuard(self.jev_guard_policy)
        self.registry = build_tool_registry(
            tool_config_dir=self.tool_config_dir,
            runtime_context={"base_dir": self.base_dir},
        )
        self.workflow_engine = WorkflowEngine(self.workflow_dir)
        self.package_catalog = PackageCatalog(self.workflow_dir)
        self.custom_tool_specs: list[ToolSpec] = []
        self.sessions: dict[str, GuardSession] = {}
        self.in_guards: dict[str, InGuard] = {}
        self.logger = setup_file_logger(self.base_dir)
        self.logger.info("GuardGatewayService 已启动，policy_dir=%s", self.policy_dir)

    def build_context(self, user_id: str, user_request: str) -> dict[str, Any]:
        # Pre-Guard：在外部 Agent 开始规划前，先生成它能看到的业务规则、权限和工具白名单。
        permissions = load_user_permissions(user_id=user_id, policy_dir=self.policy_dir)
        user_id = permissions.user_id
        in_guard = InGuard(
            permissions=permissions,
            registry=self.registry,
            policy=self.in_guard_policy,
            jev_guard=self.jev_guard,
        )
        pre_guard = PreGuard(
            permissions=permissions,
            registry=self.registry,
            pre_policy=self.pre_guard_policy,
            in_policy=self.in_guard_policy,
            packages=self.package_catalog,
        )
        context = pre_guard.build_context(user_request)
        context["semantic_guard"] = {
            "enabled": self.jev_guard_policy.enabled,
            "provider": self.jev_guard_policy.provider,
            "note": "JEV 只做语义风险评分和转人工建议；权限、白名单、Schema 仍由 In-Guard 硬拦截。",
        }
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
                "jev_enabled": self.jev_guard_policy.enabled,
            },
        )

        return {
            "session_id": session_id,
            "context": context,
            # 对 QwenPaw / DeerFlow 这类外部平台来说，重点是保存 session_id。
            "integration_note": "外部平台后续业务工具调用必须携带 session_id 走 /tools/call。",
        }

    def register_tool(self, tool: ToolSpec) -> None:
        """注册其他业务域工具，使其可经 guarded_tool_call 受控调用。"""
        self.registry.register(tool)
        self.custom_tool_specs.append(tool)

    def run_workflow(
        self,
        user_request: str,
        workflow_name: str | None = None,
        user_id: str = "default",
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行配置文件声明的受控工作流，是所有业务场景的通用入口。"""
        if workflow_name is None:
            package = self.package_catalog.match(user_request)
            if package is None:
                raise ValueError("未匹配到业务包；请补充业务关键词或显式提供 workflow_name。")
            workflow_name = package["_workflow_name"]
        workflow = self.workflow_engine.load(workflow_name)
        context_response = self.build_context(user_id=user_id, user_request=user_request)
        session_id = context_response["session_id"]
        session = self.sessions[session_id]
        session.context["task_type"] = workflow.task_type
        run = self.workflow_engine.run(
            workflow,
            inputs or {},
            lambda tool_name, arguments: self.call_tool(session_id, tool_name, arguments),
        )
        if run["blocked"]:
            return self._blocked_workflow(
                session_id=session_id,
                context_response=context_response,
                tool_results=run["tool_results"],
                reason=run["reason"],
            )
        review = self.review_output(session_id=session_id, final_answer=run["final_answer"])
        return {
            "status": "success" if review["passed"] else "review_failed",
            "session_id": session_id,
            "context": context_response["context"],
            "workflow": workflow_name,
            "tool_results": run["tool_results"],
            "review": review,
            "final_answer": run["final_answer"] if review["passed"] else None,
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
            "next_action": (
                "调用 guarded_attempt_start 开启新一轮，再按 tool_schemas 重试。"
                if not result.allowed
                else None
            ),
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
        jev_decision = self.jev_guard.review_output(final_answer)
        reasons = list(review.reasons)
        if not jev_decision.allowed:
            reasons.append(f"JEV 输出语义风险：{jev_decision.reason}")
        passed = review.passed and jev_decision.allowed
        response = {
            "attempt_no": session.attempt_no,
            "passed": passed,
            "reasons": reasons,
            "jev_decision": {
                "action": jev_decision.action,
                "risk_score": jev_decision.risk_score,
                "confidence": jev_decision.confidence,
                "reason": jev_decision.reason,
                "source": jev_decision.source,
            },
            "action": "allow_output" if passed else "retry_or_human_confirm",
            "message": "复核通过，可以输出给用户。" if passed else "复核失败，请按原因重试或转人工。",
        }
        self.logger.info(
            "Post-Guard output_review session_id=%s attempt_no=%s passed=%s reasons=%s",
            session_id,
            session.attempt_no,
            passed,
            reasons,
        )
        append_jsonl(
            self.base_dir,
            "audit.jsonl",
            {
                "event": "output_review",
                "session_id": session_id,
                "attempt_no": session.attempt_no,
                "passed": passed,
                "reasons": reasons,
                "jev_action": jev_decision.action,
                "jev_risk_score": jev_decision.risk_score,
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
        self.pre_guard_policy = load_pre_guard_policy(self.policy_dir)
        self.in_guard_policy = load_in_guard_policy(self.policy_dir)
        self.post_guard_policy = load_post_guard_policy(self.policy_dir)
        self.jev_guard_policy = load_jev_guard_policy(self.policy_dir)
        self.jev_guard = JevGuard(self.jev_guard_policy)
        self.registry = build_tool_registry(
            tool_config_dir=self.tool_config_dir,
            runtime_context={"base_dir": self.base_dir},
        )
        self.package_catalog = PackageCatalog(self.workflow_dir)
        for tool in self.custom_tool_specs:
            self.registry.register(tool)
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
    def _blocked_workflow(
        session_id: str,
        context_response: dict[str, Any],
        tool_results: list[dict[str, Any]],
        reason: str | None,
    ) -> dict[str, Any]:
        # 统一返回“工作流被阻断”的结构，调用方可以据此转人工或重新授权。
        return {
            "status": "blocked",
            "session_id": session_id,
            "context": context_response["context"],
            "tool_results": tool_results,
            "review": {
                "passed": False,
                "reasons": [reason or "工作流被工具拦截。"],
                "action": "human_confirm",
            },
            "final_answer": None,
        }
