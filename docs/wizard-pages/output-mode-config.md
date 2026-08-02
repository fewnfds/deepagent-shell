# 输出模式

输出模式只管“LangChain 运行事件怎样变成调用方收到的字符串”。它不修改 Agent state、提示词或
工具，也不进入 `create_deep_agent()` constructor。每个 Primary 必须选择一套输出模式。

Runtime 使用 `astream_events(version="v3")`。归一事件先进入请求级输出整流器；对外任意时刻最多只有
一个事件正在输出，其他事件按首次可见顺序排队。reasoning/text 在模板边界可预先确定时逐 delta 真
流式输出，工具调用、工具结果及其他事件仍以完整事件为单位。完整 tool call 会在当前模型周期内等待
匹配的 result/error，再按 `tool_call_id` 成对相邻输出；周期结束仍缺少结果时调用会单独输出，不阻塞
下一周期。关闭 reasoning/text 不会阻止纯工具或其他事件独立输出。非流式响应消费同一整流后序列，
所以两种传输完成后的正文逐字一致。

## Payload

```json
{
  "name": "普通聊天",
  "filter_mode": "blocklist",
  "filter_mappings": [],
  "variable_encoding": "plain",
  "event_templates": {
    "assistant_text": {"enabled": true, "template": "{{message}}"},
    "reasoning": {"enabled": true, "template": "<details><summary>*Reasoning*</summary>\n{{message}}\n\n*name={{agent_name}}* | *seq={{sequence}}* | *id={{message_id}}*\n─────────\n</details>\n"},
    "tool_call": {"enabled": true, "template": "<details><summary>*Tool Call {{tool_name}}*</summary>\n{{message}}\n\n*event={{phase}}* | *seq={{sequence}}* | *id={{tool_call_id}}*\n─────────\n</details>\n"},
    "tool_result": {"enabled": true, "template": "<details><summary>*Tool Result {{tool_name}}*</summary>\n{{message}}\n\n*status={{status}}* | *seq={{sequence}}* | *id={{tool_call_id}}*\n─────────\n</details>\n"},
    "tool_error": {"enabled": true, "template": "<details><summary>*Tool Error {{tool_name}}*</summary>\n{{message}}\n\n*status={{status}}* | *code={{error_code}}* | *seq={{sequence}}* | *id={{tool_call_id}}*\n─────────\n</details>\n"},
    "subagent": {"enabled": true, "template": "<details><summary>*Subagent {{subagent_name}}*</summary>\n{{message}}\n\n*event={{phase}}* | *status={{status}}* | *seq={{sequence}}* | *call={{tool_call_id}}*\n─────────\n</details>\n"},
    "custom": {"enabled": true, "template": "<details><summary>*Custom {{channel}}*</summary>\n{{message}}\n\n*event={{phase}}* | *seq={{sequence}}*\n─────────\n</details>\n"},
    "lifecycle": {"enabled": true, "template": "<details><summary>*Agent Status {{status}}*</summary>\n{{message}}\n\n*event={{phase}}* | *seq={{sequence}}* | *finish={{finish_reason}}* | *code={{error_code}}*\n─────────\n</details>\n"}
  }
}
```

`event_templates` 必须恰好包含当前八类事件，每类只有 `enabled + template`。开启的模板不能为空；
旧的 `start_template`、`finish_template` 和 `other` 事件不属于当前结构。

模板只替换本页【事件与变量】列出的 `{{variable}}`，不执行表达式、条件或函数。每段模板最多
100,000 字符。事件目录、可用变量和新建草稿默认值来自服务端管理 catalog；编辑器不再为每个模板
重复显示变量下拉，只负责编辑和机械组装 payload，事件键、字段及变量是否合法仍由服务端校验。
变量占位符必须使用完整、成对的双花括号。少一侧括号、使用当前事件不支持的变量，或启用了空模板时，
校验报告会直接指出具体事件模板、问题原因和修改方向；不要求用户从通用“内容不符合要求”中猜测。

新建输出模式默认开启全部八类事件。模型回答仍只输出 `{{message}}`；其余七类使用可折叠的
`<details>` 模板，正文后固定空一行，再显示必要的名称、状态、序号或 ID，作为可直接修改的参考。
页面把【高级变量与编码】放在事件模板之前，默认使用 `plain` 原样插入变量值。

`variable_encoding=html` 只转义插入的变量值，模板本身不转义；`plain` 原样插入。OpenAI JSON/SSE
编码仍由 API 层负责。

## 完整事件来源

LangChain v3 的消息事件不是三个可以互换的正文节点：

- `message-start`：用于关联一次模型消息及其 Provider/model 提示；
- text/reasoning `content-block-start`：建立稳定 block identity；成为当前事件时，先输出模板中
  `{{message}}` 之前的内容；
- text/reasoning `content-block-delta`：当前事件逐段输出经过所选编码的 message，排队事件先缓存；
- `content-block-finish.content`：一个完整的 text、reasoning 或 tool-call content block，是对应公开
  事件的最终 snapshot；真流式时只补充尚未出现在 delta 中的确定尾部，不决定模板关闭，也不覆盖
  已交付内容；
- `message-finish`：在请求内完成 usage、finish reason 和 block 完整性归一化，不清空公开事件池；模型随后
  触发的工具结果仍属于这一输出周期；持久 workflow timeline 只保存标准 usage 数字、finish reason 与固定
  完整性计数；
- 下一次 Primary 流式 `message-start` 或非流式完整 `AIMessage`：先排空上一次模型调用及其后续工具
  活动留下的事件，再开始新周期；
- `tool-finished.output`：工具执行的完整最终结果；`tool-output-delta` 不公开。

一个模型消息可以包含多个 block。公开顺序以 block start 或完整原子事件首次可见顺序为准，不按迟到
finish 的到达顺序重排。一次输出周期从 Primary 流式 `message-start` 或非流式完整 `AIMessage` 开始，
包含该模型调用产生的 block 和随后 Agent 执行产生的工具/Subagent 结果，到下一次 Primary 模型消息前
结束。输出整理不改变多轮 tool loop。

真流式采用“落笔无悔”语义：已发送 delta 不撤销、不覆盖。只有黑名单模式、无过滤映射且模板恰好
包含一个 `{{message}}` 时才在首字节前确定可以流式；其他配置等待完整 block 后原子投影。若 finish
snapshot 与已交付 delta 不一致，客户端已收到的 delta 保持事实，差异只记录到 management-only 模型
响应诊断，不因此中止 Agent。

当新事件已经排队、当前 reasoning/text 却没有及时 finish 时，整流器只允许当前 block 在一秒静默窗口
内由相同 identity 的新 delta 续流；窗口结束就完整输出当前模板后缀并让出。极迟的同 block 内容会作为
新的同类型 continuation 完整包裹，绝不会进入另一个事件模板。reasoning/text 的这项有限续流能力不是
插队权；工具和其他启用事件到达队首后同样会输出，不能被饿死。

## 事件与变量

所有事件都有 `event_type`、`phase`、`sequence`、`timestamp`、`namespace`、`agent_name`、`node`、
`message`。额外变量如下：

| 事件 | 权威来源 | 额外变量 |
| --- | --- | --- |
| `assistant_text` | Primary text `content-block-finish` | `message_id` |
| `reasoning` | Primary reasoning `content-block-finish` | `message_id` |
| `tool_call` | 完整 tool-call content block | `tool_name`、`tool_call_id`、`arguments` |
| `tool_result` | `tool-finished` 或完整 server tool result | `tool_name`、`tool_call_id`、`status`、`output` |
| `tool_error` | tool failed/error 或无效完整 tool call | `tool_name`、`tool_call_id`、`status`、`error_code` |
| `subagent` | Subagent lifecycle | `subagent_name`、`tool_call_id`、`status` |
| `custom` | 显式 `custom` / `custom:*` 原子事件 | `channel`、`data_json` |
| `lifecycle` | Agent Shell 顶层运行边界 | `status`、`finish_reason`、`error_code` |

只有最外层 Primary 的模型 text/reasoning block 进入公开输出。Subagent 内部模型内容不公开；它的
最终回答仍通过匹配 `tool_call_id` 的完整工具结果返回。

未知 method、未知工具事件和不支持的媒体 block 默认不进入输出模板。`values`、`updates`、`tasks`、
`checkpoints`、`input`、`debug`、Provider 原始响应和内部 state 不进入模板和普通 API/DOM。LangChain
已标准化的 finished content blocks 与 Provider metadata 只参与本次请求内的输出归一化，不进入 workflow
timeline。

## 过滤

`filter_mappings` 是最多 100 条“事件字段 → 匹配值”。字段和值区分大小写，使用字符串精确匹配，
不执行正则或表达式。字段有两种写法：

- `tool_result.tool_name → commit`：只匹配 `tool_result` 事件中的 `tool_name=commit`；
- `tool_name → commit`：匹配任何确实包含 `tool_name` 且值为 `commit` 的事件。

多条条件使用“任一条命中”。`allowlist` 只放行命中任一条件的事件，`blocklist` 排除命中任一条件的
事件。空数组不匹配任何事件，所以白名单会阻拦全部事件，黑名单会放行全部事件。字段可以从页面
建议项选择，也可以按 `field` 或 `event_type.field` 格式输入；值长度为 1–4096 字符。

## 失败与取消

正常完成之前由 Provider/LangChain 报告的错误、既有超时、step limit、取消和客户端断开不会伪装成
正常完成。真流式已经交付的 delta 无法撤回；顶层请求错误继续通过稳定 OpenAI-compatible 错误边界
返回，不能通过关闭 `tool_error` 或 `lifecycle` 隐藏。v3 若缺少某个 `content-block-finish`，Shell 在下一
模型周期或 graph EOF 用已经收到的 delta 收敛模板边界并记录 `incomplete_block_count`，不会据此终止
Agent。仍可向客户端发送错误正文时，当前模板后缀会先于 lifecycle error 输出；客户端已经断开时只
清理本地状态并传播取消。

## 使用范围与旧记录

输出模式与模型同为 Primary 必选能力；Primary 页面不能清除，管理 API 也拒绝缺失引用。
流式、非流式和 Provider 前拦截测试都使用所选模式，不存在隐藏的默认投影。结构化 token usage
继续位于 OpenAI 响应字段，不复制成聊天正文事件。

项目不自动迁移或补齐旧输出模式。配置仓库会保留不符合当前八类单模板结构的完整原始 JSON；记录
可载入编辑器修复，编辑草稿只投影当前 catalog 中的字段和事件，缺失或类型错误的值使用当前默认，
未知事件不进入草稿。只有用户明确保存才覆盖为新的当前结构；复制和 runtime 都会由服务端重新校验，
无效记录不会继续运行。
