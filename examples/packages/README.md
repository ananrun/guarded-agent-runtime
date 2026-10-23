# 示例业务包说明

两个示例的文件契约完全相同；差别只在业务字段和工作流步骤。

每个业务包包含：package.json（包身份、匹配关键词、业务规则）、tools.json（工具与数据或外部接口的映射）、workflow.json（工具执行顺序与阻断条件）、data.json（本地模拟数据或模拟工具返回）、demo.json（演示请求，不参与生产调用）。

## data.json 的示例约定

- datasets：原始业务数据。示例中的报销单列表放在这里。
- tool_results：工具的模拟返回值。每个键对应 tools.json 中 operation 的 source 和 key。

data.json 不是框架规则，也不是用户对话输入；它只是本地演示时替代数据库、算法服务或外部 API 的数据源。datasets 和 tool_results 是示例统一约定，不限制真实外部系统的返回字段。

报销示例同时演示两类数据：先从 datasets.forms 读取原始单据，再从 tool_results 读取发票核验、金额计算、审计意见等服务返回。

设备诊断示例只有 tool_results：状态准备、三比值、故障树等本应由不同算法或平台提供，示例直接固定其返回结果。

生产接入时，通常保留 package.json、tools.json、workflow.json，并将 tools.json 的 callable 指向外部适配器；此时不需要 data.json。
