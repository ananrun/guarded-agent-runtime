from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.planner import MockAgent
from guards.in_guard import InGuard
from guards.post_guard import PostGuard
from guards.pre_guard import PreGuard


@dataclass
class AgentLoop:
    pre_guard: PreGuard
    agent: MockAgent
    in_guard: InGuard
    post_guard: PostGuard
    max_loop: int = 3

    def run(self, user_request: str) -> dict[str, Any]:
        context = self.pre_guard.build_context(user_request)
        observations: list[dict[str, Any]] = []
        feedback: list[str] = []
        attempts: list[dict[str, Any]] = []
        final_answer: dict[str, Any] | None = None

        for attempt in range(1, self.max_loop + 1):
            attempt_results = []
            attempt_log_start = len(self.in_guard.call_log)
            thoughts = []

            for _ in range(10):
                decision = self.agent.plan(
                    model_context=context,
                    feedback=feedback,
                    observations=observations,
                    attempt=attempt,
                )
                thoughts.append(decision.thought)

                for call in decision.tool_calls:
                    result = self.in_guard.execute(
                        call, allowed_tools=context["tool_policy"]["allowed_tools"]
                    )
                    as_dict = {
                        "tool": result.tool,
                        "allowed": result.allowed,
                        "result": result.result,
                        "reason": result.reason,
                    }
                    observations.append(as_dict)
                    attempt_results.append(as_dict)

                if decision.final_answer is not None:
                    final_answer = decision.final_answer
                    break
                if not decision.tool_calls:
                    final_answer = None
                    break

            attempt_call_log = self.in_guard.call_log[attempt_log_start:]
            review = self.post_guard.review(
                final_answer=final_answer,
                observations=observations,
                call_log=attempt_call_log,
            )

            attempts.append(
                {
                    "attempt": attempt,
                    "thoughts": thoughts,
                    "tool_results": attempt_results,
                    "final_answer": final_answer,
                    "post_guard_passed": review.passed,
                    "post_guard_reasons": review.reasons,
                }
            )

            if review.passed:
                return {
                    "runtime_status": "success",
                    "task_type": context["task_type"],
                    "attempts": attempts,
                    "tool_call_log": self.in_guard.call_log,
                    "final_output": final_answer,
                }

            feedback = [
                "请重新规划并生成审核意见：",
                *review.reasons,
                "必须基于真实工具返回；餐费和保险费不得计入项目A；不得包含付款或预算修改承诺。",
            ]

        return {
            "runtime_status": "failed_needs_human_confirmation",
            "task_type": context["task_type"],
            "completed_steps": self._completed_steps(observations),
            "unsatisfied_constraints": feedback[1:-1],
            "why_not_automatic": "达到最大 Agent Loop 次数后仍未通过事后复核。",
            "manual_actions_needed": [
                "人工确认 Agent 是否需要重新授权付款或预算修改权限。",
                "人工复核不可计入项目A的费用与项目限额处理。",
                "替换或修正不遵守反馈的 Agent 策略。",
            ],
            "attempts": attempts,
            "tool_call_log": self.in_guard.call_log,
            "last_final_output": final_answer,
        }

    @staticmethod
    def _completed_steps(observations: list[dict[str, Any]]) -> list[str]:
        names = []
        for item in observations:
            if item["allowed"] and item["tool"] not in names:
                names.append(item["tool"])
        return names
