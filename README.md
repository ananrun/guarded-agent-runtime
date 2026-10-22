# Guarded Agent Runtime

面向 QwenPaw、DeerFlow 等 Agent 平台的**报销审核安全网关**。它通过 MCP 或 HTTP 接入 Agent，把报销业务工具统一放到受控链路中执行。

项目目录与关键文件说明见 [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md)。

它做四件事：

1. **Pre-Guard**：按用户身份生成权限、业务规则、工具白名单和 Agent 约束。
2. **In-Guard**：每次工具调用先做权限、白名单、Schema、禁止动作校验。
3. **JevOS 语义门禁**：调用本机 Jev 模型识别付款承诺、预算/发票修改、无条件全额报销等风险。
4. **Post-Guard**：最终回答必须有真实工具依据，且不得包含越权承诺。

> 这是一个网关，不是聊天 Agent。必须把它注册到外部平台；平台直接调用真实业务工具时，本项目无法拦截。

## 1. 整体流程

```text
用户
  ↓
QwenPaw / DeerFlow Agent
  ↓ MCP 或 HTTP
Guarded Agent Runtime
  ├─ Pre-Guard：权限、规则、工具白名单
  ├─ In-Guard + JevOS：工具调用风险校验
  ├─ 受控业务工具：读报销单、验票、计算、生成审核意见
  └─ Post-Guard + JevOS：最终输出复核
  ↓
Agent 输出审核结果
```

推荐外部 Agent 只调用一个入口：

```text
guarded_expense_audit
```

它会在内部完成完整审核链路，无需 Agent 自行编排 `context → tools → review`。

## 2. 前置条件

- Python 3.10+。
- MCP 模式需要安装 `mcp` 包。
- JevOS 本机模型与运行环境位于 `D:\jev`。

进入项目目录并安装依赖：

```powershell
cd E:\.Aproject\desktop\Ontology\guarded-agent-runtime
pip install -r requirements.txt
```

## 3. 启动 JevOS（必需）

新开一个 PowerShell 窗口，保持运行：

```powershell
Set-Location 'D:\jev\routeA\jev-windows-x64\jev'
.\jev.exe serve
```

检查服务：

```powershell
Invoke-RestMethod 'http://127.0.0.1:8017/health'
```

必须看到：

```json
{ "status": "ready", "model": "jevos-v5" }
```

项目通过 `config/policies/jev.json` 使用 JevOS：

```json
{
  "provider": "jevos_http",
  "base_url": "http://127.0.0.1:8017",
  "failure_mode": "deny"
}
```

`failure_mode: "deny"` 表示 JevOS 不可用时，语义门禁默认拒绝，不会静默降级。

## 4. 本地验证

先确认 MCP 服务和完整审核流程正常：

```powershell
$env:PYTHONIOENCODING='utf-8'
python mcp_smoke_test.py
```

成功标准：输出包含 `guarded_expense_audit`，并且审核结果为：

```json
{
  "status": "success",
  "review": {
    "passed": true,
    "jev_decision": { "source": "jevos_http" }
  }
}
```

需要本地查看“正常审核 / 违规拦截”完整示例时运行：

```powershell
python external_platform_demo.py
```

示例数据包含两张报销单：`EXP-2026-001` 可通过；`EXP-2026-002` 含重复发票和缺失票据，会返回 `status: "blocked"`。通过 MCP 或 HTTP 调用时传入 `expense_id: "EXP-2026-002"` 即可验证失败分支。

## 5. 注册为 MCP Server

在 QwenPaw、DeerFlow 或其他支持 stdio MCP 的平台中，添加以下配置：

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

如果平台找不到 `python`，把 `command` 替换成 Python 的完整路径，例如：

```json
"command": "D:\\Python\\Python313\\python.exe"
```

注册后重启或刷新 MCP 客户端，确认平台能看到：

```text
guarded_expense_audit
```

### 如何启动 MCP 服务

MCP 使用 stdio 协议，通常**不需要手动启动**：平台读取上面的配置后，会自动执行：

```powershell
python -m gateway.mcp_server
```

手动执行该命令时进程会等待客户端连接，终端没有普通输出是正常行为。不要用它是否有输出判断成功与否；使用以下命令验证：

```powershell
python mcp_smoke_test.py
```

## 6. 查看 MCP 调用记录

MCP 使用 stdout 通信，因此后台记录写入本项目的 `logs/` 目录，不会出现在 MCP 终端中：

```powershell
cd E:\.Aproject\desktop\Ontology\guarded-agent-runtime
Get-Content .\logs\guard_gateway.log -Wait -Encoding UTF8
Get-Content .\logs\audit.jsonl -Wait -Encoding UTF8
```

- `guard_gateway.log`：便于人工阅读的运行日志。
- `audit.jsonl`：一行一条结构化事件，包含 `session_id`、工具名、参数、是否放行、拦截原因和 Jev 风险结果。

也可以让 MCP 客户端调用：

```text
guarded_audit_logs
```

传入 `session_id` 可查看某一次任务的内存调用记录；持久化历史以 `logs/audit.jsonl` 为准。

## 7. 配置 Agent 调用规则

MCP 注册仅让 Agent“看见工具”，不会保证它一定调用。因此需在平台的工作流/意图路由/Agent Instructions 中加入：

```text
当用户请求涉及报销、差旅或费用审核时，优先调用 guarded_expense_audit。
不要直接调用付款、预算修改、发票修改、数据库、文件系统或 Shell 工具。
```

然后在平台中输入：

```text
帮我审核报销单
```

正确调用链为：

```text
Agent → guarded_expense_audit → Pre-Guard → In-Guard/JevOS
      → 受控业务工具 → Post-Guard/JevOS → Agent 回复用户
```

## 8. MCP 工具说明

生产环境优先使用：

| 工具 | 用途 |
| --- | --- |
| `guarded_expense_audit` | 一站式报销审核，推荐给外部 Agent 使用。 |

以下工具只适合需要自行编排流程的调试或工作流场景：

| 工具 | 用途 |
| --- | --- |
| `guarded_context_build` | 创建受控上下文并返回 `session_id`。 |
| `guarded_tool_call` | 通过 In-Guard 调用任意已注册业务工具。 |
| `guarded_output_review` | 复核 Agent 候选输出。 |
| `guarded_attempt_start` | 开启一次新的重试轮次。 |
| `guarded_audit_logs` | 查询会话内调用日志。 |
| `guarded_policy_reload` | 重新加载规则。 |

手动编排时顺序必须是：

```text
guarded_context_build
  → guarded_tool_call
  → guarded_output_review
```

复核失败后先调用 `guarded_attempt_start`，再开始下一轮工具调用。

## 9. 扩展到其他业务场景

网关核心不是报销专用的：`guarded_context_build`、`guarded_tool_call`、`guarded_output_review` 对任何已注册业务工具都适用。`guarded_expense_audit` 只是报销 Demo 的快捷入口。

在你的启动代码中注册新工具：

```python
from gateway.mcp_server import service
from tools.tool_registry import ToolSpec

def query_contract(contract_id: str) -> dict:
    return {"contract_id": contract_id, "status": "active"}

service.register_tool(ToolSpec(
    name="query_contract",
    func=query_contract,
    required_permission="contract:read",
    schema={"contract_id": str},
))
```

随后在 `users.json` 给用户添加 `contract:read` 权限，外部 Agent 就能通过：

```text
guarded_context_build → guarded_tool_call(tool_name="query_contract") → guarded_output_review
```

非报销任务会采用通用输出复核：仍拦截越权承诺和 Jev 语义风险，但不强制报销金额、票据和报销工具依据。

## 10. HTTP 接入（不支持 MCP 时）

启动 HTTP 网关：

```powershell
cd E:\.Aproject\desktop\Ontology\guarded-agent-runtime
python app.py --host 127.0.0.1 --port 8765
```

调用一站式审核接口：

```powershell
$body = @{ user_id = 'auditor_001'; user_request = '帮我审核报销单' } |
  ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri 'http://127.0.0.1:8765/expense/audit' `
  -ContentType 'application/json' `
  -Body $body
```

常用接口：

```text
POST /expense/audit       一站式审核
POST /context/build       Pre-Guard
POST /tools/call          In-Guard 工具代理
POST /review/output       Post-Guard
POST /attempt/start       新一轮重试
POST /policies/reload     重载规则
GET  /audit/logs          查询审计日志
```

## 11. 配置、日志与排错

规则目录：`config/policies/`

| 文件 | 修改内容 |
| --- | --- |
| `users.json` | 用户、角色、权限、别名。 |
| `business_rules.json` | 限额、费用类型、票据规则。 |
| `in_guard.json` | 禁止动作、白名单、参数校验。 |
| `post_guard.json` | 输出证据、必填字段、禁止承诺。 |
| `jev.json` | JevOS 地址、模型、阈值、风险短语、故障策略。 |

修改配置后重载：

```text
MCP：guarded_policy_reload
HTTP：POST /policies/reload
```

重载会清空已有 session，正在进行的任务需要重新开始。

实时日志：

```powershell
Get-Content .\logs\guard_gateway.log -Wait -Encoding UTF8
Get-Content .\logs\audit.jsonl -Wait -Encoding UTF8
```

正常日志顺序：

```text
context_build → tool_call（多次）→ output_review（passed=true）
```

常见问题：

| 现象 | 处理 |
| --- | --- |
| `guarded_expense_audit` 不出现 | 刷新 MCP 客户端；检查 `cwd`、Python 路径和 `mcp_smoke_test.py`。 |
| `JevOS 语义判定不可用` | 运行 `Invoke-RestMethod http://127.0.0.1:8017/health`，确认 JevOS 正在运行。 |
| 日志没有新增 | Agent 没有调用网关工具，检查第 7 节的路由/Instructions。 |
| Agent 仍说“已付款” | 禁用其直连业务工具，并确认最终输出经过 `guarded_output_review`。 |

## 12. 安全边界

本项目只能约束**经过它的调用**。要有效生效，外部 Agent 必须只获得 `guarded_*` 工具；真实付款、预算、数据库、文件系统和 Shell 工具不能同时直接暴露给 Agent。
