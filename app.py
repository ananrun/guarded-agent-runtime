from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent.planner import MockAgent
from guards.in_guard import InGuard
from guards.post_guard import PostGuard
from guards.pre_guard import PreGuard
from policies.permissions import load_user_permissions
from policies.rules import load_business_rules
from runtime.loop import AgentLoop
from tools.tool_registry import build_expense_tool_registry


def build_runtime(scenario: str, max_loop: int) -> AgentLoop:
    base_dir = Path(__file__).resolve().parent
    data_path = base_dir / "data" / "sample_expense.json"

    rules = load_business_rules()
    permissions = load_user_permissions(user_id="auditor_001")
    registry = build_expense_tool_registry(data_path=data_path, rules=rules)

    pre_guard = PreGuard(rules=rules, permissions=permissions, registry=registry)
    in_guard = InGuard(rules=rules, permissions=permissions, registry=registry)
    post_guard = PostGuard(rules=rules, permissions=permissions)
    agent = MockAgent(mode=scenario)

    return AgentLoop(
        pre_guard=pre_guard,
        agent=agent,
        in_guard=in_guard,
        post_guard=post_guard,
        max_loop=max_loop,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded Agent Runtime demo")
    parser.add_argument(
        "--scenario",
        choices=["normal", "violation", "recover"],
        default="normal",
        help=(
            "normal: compliant audit; violation: stubborn unsafe agent until max loop; "
            "recover: unsafe first attempt, corrected second attempt"
        ),
    )
    parser.add_argument("--max-loop", type=int, default=3)
    parser.add_argument(
        "--request",
        default="帮我审核这张差旅报销单，能报的直接生成审核意见。",
    )
    args = parser.parse_args()

    runtime = build_runtime(scenario=args.scenario, max_loop=args.max_loop)
    report = runtime.run(user_request=args.request)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
