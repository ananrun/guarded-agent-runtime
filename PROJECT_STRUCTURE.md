# 项目结构

核心主线只有三层 Guard；其余目录只是接入、执行和配置支撑。

```text
gateway/  →  guards/pre_guard.py  →  guards/in_guard.py  →  guards/post_guard.py
  接入            事前约束                 事中拦截                 事后复核
```

```text
guarded-agent-runtime/
├─ gateway/       MCP、HTTP、会话和审计编排
├─ guards/        Pre / In / Post Guard 与 JevOS 门禁
├─ framework/     业务包发现和声明式工作流执行
├─ tools/         工具注册、配置数据适配、调用数据结构、沙箱
├─ policies/      通用策略与用户权限配置加载
├─ config/        框架级策略及字段说明（不含业务）
├─ packages/      生产业务包挂载目录，默认为空
├─ examples/      独立示例业务包，默认不加载
├─ logs/          运行与审计日志
├─ app.py         HTTP 入口
├─ mcp_smoke_test.py  MCP 验证脚本
└─ README.md      使用与接入说明
```

业务包必须放入 `packages/<名称>/`，并至少包含：

```text
package.json      包名、任务类型、关键词、规则、文件清单
tools.json        工具定义
workflow.json     工作流定义
```

需要数据、领域模型或演示时，再增加 `data.json`、`domain_model.json`、`demo.json`。也可用环境变量 `GUARDED_PACKAGE_DIR` 指定项目外的业务包目录。
