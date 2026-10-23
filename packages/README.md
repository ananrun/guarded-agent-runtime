# 业务包说明

一个业务包就是一个独立文件夹。框架只读取它，不把规则写入框架代码。

```text
packages/<包名>/
├─ package.json       # 必选：包元信息、识别关键词、业务规则
├─ tools.json         # 必选：可调用工具及权限、参数契约
├─ workflow.json      # 必选：工具执行顺序、拦截条件、最终输出
├─ data.json          # 可选：配置数据、模拟数据、预置查询结果
├─ rules.json         # 可选：公式、条件和命中结果，由框架规则引擎计算
├─ domain_model.json  # 可选：对象、关系、公理、领域约束
└─ demo.json          # 可选：本地/MCP 演示请求
```

## `package.json`

框架通过此文件识别包，并校验必选文件是否存在。

```json
{
  "name": "contract_review",                 
  "task_type": "contract_review",            
  "keywords": ["合同", "审查"],               
  "files": {"workflow": "workflow.json", "tools": "tools.json"},
  "rules": {},                                
  "model_instructions": ["只能使用当前包工具。"]
}
```

- `name`：包唯一名称；工具归属和隔离依据。
- `task_type`：任务类型标识。
- `keywords`：用户请求包含其中任一词时，Pre-Guard 选择此包。
- `files`：必须声明 `workflow`、`tools`；可补充 `data`、`rules`、`domain_model`、`demo`。
- `rules`：原样传入受控上下文，由工作流或外部适配器使用。
- `model_instructions`：当前包给 Agent 的约束。

## `tools.json`

声明工具，不写业务实现代码。

```json
{
  "provider_factory": "tools.configured_provider:create_provider",
  "data_file": "data.json",
  "tools": [{
    "name": "read_contract",
    "operation": {"kind": "find", "source": "contracts", "match_argument": "contract_id"},
    "required_permission": "contract:read",
    "schema": {"contract_id": "str"}
  }]
}
```

- `name`：全局唯一工具名。
- `required_permission`：调用人必须拥有的权限；在 `config/users.json` 配置。
- `schema`：参数及类型；支持 `str`、`int`、`float`、`bool`、`dict`。
- `operation`：配置数据适配器的操作，支持 `list`、`find`、`lookup`。
- `data_file`：相对于当前业务包目录的配置数据文件；通常写 `data.json`。
- `callable`：真实外部系统可改用 `"外部模块:函数"`；适配器应放在框架项目外。

### 参数化规则计算

`tools.json` 声明 `rule_file` 后，工具可使用 `rule_evaluate`。框架从 `source` 找到当前记录，按 `rules.json` 计算派生参数并匹配规则；模型不参与计算。

```json
{
  "rule_file": "rules.json",
  "tools": [{
    "name": "evaluate_policy",
    "operation": {
      "kind": "rule_evaluate",
      "source": "datasets.records",
      "match_argument": "record_id",
      "rule_set": "policy"
    },
    "required_permission": "policy:evaluate",
    "schema": {"record_id": "str"}
  }]
}
```

`rules.json` 的 `derive` 仅支持 `add`、`subtract`、`multiply`、`divide` 和可选 `round`；规则条件支持 `all`、`any`、`eq`、`ne`、`gt`、`gte`、`lt`、`lte`、`in`。变量用 `$record...` 引用当前记录，用 `$derived...` 引用已计算参数。每次结果都会返回 `derived` 和 `matched_rules`，供审计追溯。

## `workflow.json`

声明业务流程。`tool` 执行工具；`require` 不满足时立即阻断；`assign` 派生输入。

```json
{
  "name": "contract_review",
  "task_type": "contract_review",
  "steps": [
    {"id": "contract", "kind": "tool", "tool": "read_contract", "arguments": {"contract_id": "$input.contract_id"}},
    {"kind": "require", "path": "$steps.contract.valid", "equals": true, "reason": "合同校验未通过。"}
  ],
  "output": {"status": "passed", "message": "审核完成"}
}
```

变量引用以 `$` 开头，例如 `$input.contract_id`、`$steps.contract.valid`；`??` 可提供默认值，例如 `$input.id ?? 'default-id'`。

## 可选文件

- `data.json`：仅用于配置数据/模拟数据。生产数据应通过外部适配器获取。
- `domain_model.json`：仅存领域知识，框架不解释其中字段。
- `demo.json`：给本地验证或 MCP 冒烟测试使用，不参与生产调用。
