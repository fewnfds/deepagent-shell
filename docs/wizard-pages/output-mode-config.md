# 输出模式

输出模式把 LangChain `astream_events(version="v3")` 事件转换为调用方收到的文本。它不修改 Agent
state、提示词或工具。每个 Main Agent 必须选择一套。

## 事件

| 事件 | 专用变量 |
| --- | --- |
| `assistant_text` | `message_id` |
| `reasoning` | `message_id` |
| `tool_call` | `tool_name`, `tool_call_id`, `arguments` |
| `tool_result` | `tool_name`, `tool_call_id`, `status`, `output` |
| `tool_error` | `tool_name`, `tool_call_id`, `status`, `error_code` |
| `subagent` | `subagent_name`, `tool_call_id`, `status` |
| `custom` | `channel`, `data_json` |
| `lifecycle` | `status`, `finish_reason`, `error_code` |

所有事件还可使用 `event_type`, `phase`, `sequence`, `timestamp`, `namespace`, `agent_name`, `node`,
`message`。模板使用 `{{variable}}`；启用的模板不能为空，也不能包含未知或未闭合变量。

```json
{
  "name": "普通聊天",
  "filter_mode": "blocklist",
  "filter_mappings": [],
  "variable_encoding": "plain",
  "event_templates": {
    "assistant_text": {"enabled": true, "template": "{{message}}"},
    "reasoning": {"enabled": false, "template": "{{message}}"},
    "tool_call": {"enabled": false, "template": "{{message}}"},
    "tool_result": {"enabled": false, "template": "{{message}}"},
    "tool_error": {"enabled": true, "template": "{{message}}"},
    "subagent": {"enabled": false, "template": "{{message}}"},
    "custom": {"enabled": false, "template": "{{message}}"},
    "lifecycle": {"enabled": true, "template": "{{message}}"}
  }
}
```

`allowlist` 只保留匹配项，`blocklist` 排除匹配项；映射字段由服务端 catalog 提供。
`variable_encoding=html` 对变量值做 HTML escaping，`plain` 保留原文，模板固定文本不编码。

流式与非流式响应消费同一事件投影。reasoning/text 可逐 delta 输出，工具调用及结果以完整事件输出；
同一模型周期内可匹配的 tool call/result 会相邻排列。关闭某类普通模板不隐藏顶层 API 错误。
