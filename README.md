# Guarded Agent Runtime

通用的 Agent 受控执行框架。框架代码不包含业务规则；业务以独立包接入。

## 目录

```text
gateway/    接入与编排
guards/     事前 / 事中 / 事后 + Jev
framework/  业务包发现、工作流
tools/      工具注册、数据适配、沙箱、调用结构
policies/   通用配置加载
config/     框架策略及其说明
packages/   生产业务包挂载目录
examples/   独立示例业务包
logs/       运行与审计日志
```

完整结构见 [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md)。

## 三阶段策略

```text
用户请求 → Pre-Guard（定边界）→ In-Guard（拦动作）→ Post-Guard（验结果）
```

- **事前 / Pre-Guard**：按业务包关键词识别任务，读取用户权限，只放行当前业务包中用户有权使用的工具；再把规则、工具参数契约和 Agent 约束组装为上下文。
- **事中 / In-Guard**：每次工具调用依次校验全局禁止项、注册状态、任务白名单、用户权限和参数 Schema；启用 Jev 时再做语义风险判断。任一步失败，工具不执行且写入审计日志。
- **事后 / Post-Guard**：检查本轮是否有被拦截调用、所需证据和输出字段是否齐全、是否出现禁止表述；Jev 同时复核最终文本风险。通过才允许输出，否则重试或转人工。

配置分别位于 `config/pre_guard.json`、`config/in_guard.json`、`config/post_guard.json`；Jev 的共用策略在 `config/jev.json`。字段说明见 [config/README.md](./config/README.md)。

## 启动

```powershell
cd E:\.Aproject\desktop\Ontology\guarded-agent-runtime
pip install -r requirements.txt
```

启动 HTTP 服务：

```powershell
python app.py
```

MCP 模式不需要手动启动服务：客户端按下面的配置自动执行 python -m gateway.mcp_server。

JevOS 的地址、启动目录和命令均配置在 `config/jev.json`：

```powershell
Set-Location 'D:\jev\routeA\jev-windows-x64\jev'
.\jev.exe serve
Invoke-RestMethod http://127.0.0.1:8017/health
```

## 注册 MCP

```json
{
  "mcpServers": {
    "guarded-agent-runtime": {
      "command": "python",
      "args": ["-m", "gateway.mcp_server"],
      "cwd": "E:\\.Aproject\\desktop\\Ontology\\guarded-agent-runtime",
      "env": {
        "GUARDED_PACKAGE_DIR": "D:\\business-packages"
      }
    }
  }
}
```

外部 Agent 优先调用 `guarded_workflow_run`。MCP 的 stdio 服务由客户端自动启动。

## 接入业务

将一个业务包放到 `packages/<名称>/`，或用 `GUARDED_PACKAGE_DIR` 指向项目外目录。

每个文件的职责、字段注释和最小模板见 [packages/README.md](./packages/README.md)。

```text
packages/<名称>/
├─ package.json   包名、任务类型、关键词、规则、文件清单
├─ tools.json     工具、权限、参数 Schema
└─ workflow.json  步骤、条件、输出
```

可选文件：`data.json`、`domain_model.json`、`demo.json`。框架自动发现并校验业务包；每次任务只放行当前包工具。

两种工具接入方式：

- 配置数据：`tools.configured_provider:create_provider`，支持 `list`、`find`、`lookup`。
- 外部系统：在 `tools.json` 写 `"callable": "your_adapter.module:function"`；适配器放在框架项目外。

示例包位于 `examples/packages/`，默认不加载。复制到 `packages/` 后即可使用。
两套示例包及 data.json 的含义见 [examples/packages/README.md](./examples/packages/README.md)。

## 运行与排查

```powershell
Get-Content .\logs\guard_gateway.log -Wait -Encoding UTF8
Get-Content .\logs\audit.jsonl -Wait -Encoding UTF8
python mcp_smoke_test.py
```

修改策略或业务包后，调用 `guarded_policy_reload` 或 `POST /policies/reload`。框架只约束经 `guarded_*` 入口的调用。

`config/` 下各策略文件的职责和字段说明见 [config/README.md](./config/README.md)。
