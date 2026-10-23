# 框架策略说明

本目录只放框架级通用策略，不放某个业务的规则。修改后调用 guarded_policy_reload 立即重载。

配置文件：

- users.json：用户、角色和工具权限。
- pre_guard.json：任务开始前的识别与 Agent 约束。
- in_guard.json：工具调用时的硬性拦截开关。
- post_guard.json：输出复核与阻断条件。
- jev.json：Jev 语义风险门禁及连接参数。

## users.json

- users.<用户ID>.roles：用户角色，仅用于上下文和审计。
- users.<用户ID>.allowed_actions：可调用工具的权限；"*" 表示全部允许。
- user_aliases：调用端别名映射到用户 ID；空字符串可作为默认用户。

## pre_guard.json

- general_model_instructions：每次任务都附带的约束；会与业务包的 model_instructions 合并。

业务包匹配与任务专属约束均写在它自己的 package.json 中。

## in_guard.json

- enforce_tool_whitelist：只放行当前业务包、本次任务允许的工具。
- enforce_registered_tools：拒绝未注册工具。
- enforce_user_permissions：按 users.json 检查权限。
- enforce_schema_validation：检查工具参数名、必填项和类型。
- forbidden_actions：全局禁止的工具名；业务限制应写入业务包。

## post_guard.json

- block_on_intercepted_tool_call：工具调用被拦截时，是否阻断最终输出。
- required_source_tools：最终答复必须引用的工具。
- required_output_fields：最终答复必须包含的字段。
- forbidden_output_phrases：最终答复禁止出现的全局表述。

后三项只适合所有业务共同遵守的规则。

## jev.json

- enabled：是否启用 Jev 语义风险判断；关闭后只保留确定性三阶段 Guard。
- base_url、health_path、timeout_seconds：Jev 服务地址、健康检查路径、超时。
- launcher：本地启动 Jev 的目录与命令；框架不会自动启动进程。
- failure_mode：Jev 不可用时的处理方式；deny 表示拒绝。
- human_review_risk_threshold、deny_risk_threshold：人工复核和拒绝的风险阈值。
- tool_call_gate、output_review：分别开关工具调用和最终输出的 Jev 检查。
- risky_*、risk_questions、risk_phrase_hints：全局风险提示词与提问模板，不应写业务规则。
