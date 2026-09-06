# 使用文档

这份文档说明如何把 Guarded Agent Runtime 接入 QwenPaw。当前推荐方式是：**让 QwenPaw 调用一个一站式 MCP 工具 `guarded_expense_audit`**。事前约束、事中拦截、事后复核都封装在这个工具内部，尽量减少对 Agent instructions 的依赖。

## 1. 核心结论

只注册 MCP Server 以后，QwenPaw 只会“看到工具”，不会自动知道什么时候必须调用哪个工具。

要做到接近自动，有两种方式：

```text
最佳方式：在 QwenPaw 里配置工具触发规则或 workflow 路由。
退路方式：给 QwenPaw Agent 加一条很短的 instructions，让报销审核类请求优先调用 guarded_expense_audit。
```

本项目已经把复杂流程封装成一个工具：

```text
guarded_expense_audit
```

它内部会自动执行：

```text
Pre-Guard：生成受控上下文、权限、业务规则、工具白名单、禁止动作。
In-Guard：列报销单、读报销单、验票、计算、生成意见时逐步硬拦截。
Post-Guard：复核最终答案是否可信、合规、可追溯。
```

## 2. 完整使用流程

### 第一步：进入项目目录

```powershell
cd E:\.Aproject\desktop\Ontology\guarded-agent-runtime
```

### 第二步：安装依赖

HTTP 网关只用 Python 标准库。MCP 接入需要 `mcp` 包。

```powershell
pip install -r requirements.txt
```

如果你的环境已经有 `mcp`，可以跳过。

### 第三步：确认 MCP Server 正常

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
python mcp_smoke_test.py
```

正常时会看到 `guarded_expense_audit`，以及其他调试工具：

```text
guarded_expense_audit
guarded_context_build
guarded_tool_call
guard_list_expense_forms
guard_read_expense_form
guard_check_invoice
guard_calculate_reimbursement
guard_generate_audit_opinion
guarded_output_review
guarded_attempt_start
guarded_audit_logs
guarded_policy_reload
```

### 第四步：打开日志监听窗口

重新开一个 PowerShell 窗口：

```powershell
cd E:\.Aproject\desktop\Ontology\guarded-agent-runtime
Get-Content .\logs\guard_gateway.log -Wait -Encoding UTF8
```

结构化审计日志：

```powershell
cd E:\.Aproject\desktop\Ontology\guarded-agent-runtime
Get-Content .\logs\audit.jsonl -Wait -Encoding UTF8
```

不要用下面命令有没有输出判断日志是否正常：

```powershell
python -m gateway.mcp_server
```

这是 stdio MCP Server。它通过标准输入输出和 QwenPaw 通信，不能随便往 stdout 打普通日志。运行日志会写入 `logs/` 目录。

### 第五步：在 QwenPaw 添加 MCP 客户端

在 QwenPaw 的“创建客户端 / JSON 导入”里填：

```json
{
  "mcpServers": {
    "guarded-agent-runtime": {
      "command": "python",
      "args": ["-m", "gateway.mcp_server"],
      "cwd": "E:\\.Aproject\\desktop\\Ontology\\guarded-agent-runtime",
      "env": {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1"
      }
    }
  }
}
```

如果 QwenPaw 找不到 `python`，把 `command` 改成完整路径，例如：

```json
"command": "D:\\Python\\Python313\\python.exe"
```

如果 QwenPaw 运行在 Docker、WSL 或远程服务器里，`cwd` 要改成那个环境能访问到的路径。

### 第六步：配置自动触发

如果 QwenPaw 支持工具触发规则、工作流路由或意图路由，配置：

```text
当用户请求包含：报销、差旅、费用审核
自动调用：guarded_expense_audit
```

这是真正更接近“接入后自动”的方式。

如果 QwenPaw 当前没有这种配置能力，就把这个最小提示词放进对应 Agent 的 system prompt 或 instructions：

```text
integrations/qwenpaw_agent_instructions.md
```

这份提示词只要求一件事：

```text
报销审核类请求优先调用 guarded_expense_audit。
```

三阶段流程已经封装在 `guarded_expense_audit` 内部，不再需要 QwenPaw 自己按顺序调用多个工具。

### 第七步：重启或刷新 QwenPaw 的 MCP 客户端

确认 QwenPaw 能看到：

```text
guarded_expense_audit
```

如果看不到，说明 QwenPaw 还在用旧配置或旧进程。

### 第八步：在 QwenPaw 里提问

输入：

```text
帮我审核报销单
```

正常情况下，QwenPaw 应该调用：

```text
guarded_expense_audit
```

不要再让 QwenPaw 自己编排：

```text
guarded_context_build -> guard_list_expense_forms -> guard_read_expense_form -> ...
```

这些步骤已经由 `guarded_expense_audit` 在内部强制执行。

## 3. 如何看是否正常

日志窗口应该出现类似内容：

```text
Pre-Guard context_build session_id=... user_id=auditor_001 allowed_tools=[...]
In-Guard tool_call session_id=... tool=list_expense_forms allowed=True reason=None
In-Guard tool_call session_id=... tool=read_expense_form allowed=True reason=None
In-Guard tool_call session_id=... tool=check_invoice allowed=True reason=None
In-Guard tool_call session_id=... tool=calculate_reimbursement allowed=True reason=None
In-Guard tool_call session_id=... tool=generate_audit_opinion allowed=True reason=None
Post-Guard output_review session_id=... attempt_no=1 passed=True reasons=[]
```

这些日志虽然来自 `guarded_expense_audit` 的内部步骤，但仍然完整体现事前、事中、事后。

正常标准：

```text
QwenPaw 能看到 guarded_expense_audit。
用户提问后日志有 Pre-Guard context_build。
allowed_tools 不是空列表。
日志中出现 list_expense_forms、read_expense_form、check_invoice、calculate_reimbursement、generate_audit_opinion。
最终有 Post-Guard output_review passed=True。
```

不正常信号：

```text
日志完全没有新增：QwenPaw 没有连到 MCP Server，或没有调用 guarded_expense_audit。
allowed_tools=[]：user_id 没匹配到权限，或策略没加载成功。
QwenPaw 继续问报销单号：没有调用 guarded_expense_audit，或没有重新加载最新 MCP 工具。
QwenPaw 说已经付款：没有调用 guarded_expense_audit，或仍有直连业务工具。
```

## 4. 本地模拟

执行：

```powershell
python external_platform_demo.py
```

它会展示两件事：

```text
auto_audit：模拟 QwenPaw 只调用 guarded_expense_audit，一次完成审核。
manual_violation：模拟分步调试时尝试 approve_payment，被 In-Guard 拦截。
```

## 5. HTTP 网关

如果平台不接 MCP，但支持 HTTP Tool 或 Webhook，可以启动 HTTP 网关：

```powershell
python app.py --host 127.0.0.1 --port 8765
```

一站式审核接口：

```text
POST /expense/audit
```

请求：

```json
{
  "user_id": "auditor_001",
  "user_request": "帮我审核报销单"
}
```

底层调试接口：

```text
POST /context/build
POST /tools/call
POST /review/output
POST /attempt/start
POST /policies/reload
GET  /audit/logs
```

## 6. 修改规则

编辑：

```text
config/policies/
```

可以改：

```text
users.json           用户角色、用户权限、用户别名
business_rules.json  项目A限额、不能计入项目A的费用类型、重复发票规则、缺失票据规则
pre_guard.json       任务关键词、注入给模型的约束说明
in_guard.json        工具白名单校验、注册工具校验、用户权限校验、参数校验、禁止动作
post_guard.json      必需工具依据、必需输出字段、越权承诺短语、是否因本轮拦截而复核失败
```

MCP 模式重载：

```text
guarded_policy_reload
```

HTTP 模式重载：

```text
POST /policies/reload
```

## 7. 当前 Demo 的正确结果

```text
项目A可报销金额：25000.0 元
其他渠道承担金额：5237.01 元
不可计入项目A：保险 245.0 元，伙食费 2365.89 元
超出项目A限额：2626.12 元
异常项：无
```
