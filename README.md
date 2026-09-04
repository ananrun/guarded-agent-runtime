# Guarded Agent Runtime

Guarded Agent Runtime 是一个受控智能体执行框架原型。它围绕“事前约束、事中拦截、事后复核”组织 Agent Runtime，目标是避免越权调用、非法参数、违规动作、幻觉输出和不可追溯结果。

## 三阶段约束思想

```text
用户请求
  -> Pre-Guard
  -> Agent
  -> In-Guard
  -> Tool Execution
  -> Post-Guard
  -> 通过则输出，失败则进入 Agent Loop
```

Pre-Guard 是确定性的上下文装配器。它识别任务类型、加载业务规则和用户权限、生成工具白名单、注入禁止动作，并组装模型上下文。

In-Guard 是代码级硬拦截层。它校验工具 schema、参数、权限、工具白名单和动作黑名单，并通过沙箱边界执行工具，同时记录调用日志。即使 Agent 生成了 `approve_payment` 或 `modify_budget`，也不会真正执行。

Post-Guard 是事后复核层。当前版本实现确定性规则校验器，检查结果是否来自真实工具返回、金额是否一致、业务规则是否执行、是否存在越权承诺、输出格式是否完整。

## 核心模块

```text
guarded-agent-runtime/
├── app.py
├── agent/
│   ├── planner.py
│   └── prompts.py
├── guards/
│   ├── pre_guard.py
│   ├── in_guard.py
│   └── post_guard.py
├── tools/
│   ├── expense_tools.py
│   └── tool_registry.py
├── policies/
│   ├── rules.py
│   └── permissions.py
├── runtime/
│   ├── executor.py
│   ├── sandbox.py
│   └── loop.py
├── data/
│   └── sample_expense.json
└── README.md
```

## 运行方式

无需第三方依赖，使用 Python 3.10+ 即可。

```bash
cd guarded-agent-runtime
python app.py --scenario normal
python app.py --scenario violation
python app.py --scenario recover
```

`normal` 演示合规审核。`violation` 演示 Mock Agent 持续违规，达到最大循环次数后停止自动执行。`recover` 演示首次违规，收到 Post-Guard 反馈后第二轮修正并通过。

## Demo 业务规则

差旅报销单包含机票、保险、伙食费、注册费、住宿费。项目A限额为 25000 元。

规则：

- 餐费不能从项目A报销。
- 保险费不能从项目A报销。
- 项目A报销金额不能超过 25000 元。
- 重复发票不得通过。
- 缺失票据不得通过。
- 当前用户只能生成审核意见，不能直接付款，不能修改预算。

可用工具：

- `read_expense_form`
- `check_invoice`
- `calculate_reimbursement`
- `generate_audit_opinion`

禁止动作：

- `approve_payment`
- `modify_budget`
- `modify_invoice`

## 示例结果摘要

正常审核中，合规工具链会计算：

- 项目A可报销金额：25000.00 元
- 其他渠道承担金额：5237.01 元
- 不可计入项目A的费用：保险 245.00 元、伙食费 2365.89 元
- 超出项目A限额：2626.12 元

违规案例中，Mock Agent 会尝试调用 `approve_payment` 和 `modify_budget`，In-Guard 会分别拦截；随后它还会输出“已提交付款”和错误金额，Post-Guard 会识别金额不一致、缺少真实计算依据、包含越权承诺，并触发 Agent Loop。多轮仍失败时，Runtime 会输出已完成步骤、未满足约束、无法自动完成原因和需要人工处理的动作。

## 为什么事中约束必须是代码级硬拦截

大模型只能生成文本或结构化意图，不能被当作安全边界。让模型自己判断是否越权，会受到提示注入、上下文遗漏、推理错误和幻觉影响。In-Guard 必须在真实工具执行前用确定性代码拦截，并以权限、白名单、黑名单和 schema 作为执行门禁。这样 Agent 即使“想”付款，也只能得到拦截结果，无法真的付款。

## 参考思想与区别

- LangGraph / LangChain Middleware：参考 Agent Loop、状态流转、工具调用和 Human-in-the-Loop 思路。本项目没有复刻其图执行框架，而是用最小 Runtime 明确表达三阶段边界。
- Microsoft Agent Governance Toolkit：参考运行时治理、工具拦截和策略执行思想。本项目将治理逻辑拆成 Pre/In/Post 三层。
- Open Policy Agent：参考策略引擎思想，用权限、白名单、黑名单和资源规则做确定性决策。当前版本用 Python policy 模块模拟，后续可替换为 OPA。
- NVIDIA NeMo Guardrails：参考输入、工具、输出护栏。本项目优先实现代码级工具护栏和确定性输出复核。

## 扩展建议

- 接入真实 LLM：把 `MockAgent.plan()` 替换为 LLM client，要求模型输出 `ToolCall[]` 或最终 JSON，并继续让 In-Guard 执行所有工具。
- 接入 OPA：将 `policies/rules.py` 和 `policies/permissions.py` 外置为 Rego 策略，In-Guard 在工具执行前查询 OPA decision。
- 接入 LangGraph：把 `runtime/loop.py` 拆成图节点，Pre-Guard、Agent、In-Guard、Post-Guard 分别作为节点，Post-Guard 失败边回到 Agent 节点。
- 接入 NeMo Guardrails：在 Pre-Guard 前增加输入护栏，在 Agent 输出后增加可编程对话与输出护栏，但工具执行安全仍保留 In-Guard 硬拦截。
