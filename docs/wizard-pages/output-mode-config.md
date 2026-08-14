# 输出模式

输出模式是 Main Agent 必选组件。它把规范化后的 LangChain v3 Agent 事件交给用户编写的 Python，函数返回值成为
`/v1/chat/completions` 的文本输出。它不修改 Agent State、提示词或工具。

## 编写输出脚本

每个事件类型都有独立开关和一段完整 Python 源码。源码必须只定义一个同步入口 `output(event)`；`event` 是下文定义的
稳定 `dict`，返回值必须是 `str`。

```python
def output(event):
    return event["message"]
```

例如自行拼接工具结果：

```python
def output(event):
    tool = event["tool_name"]
    return f"<tool>{tool}: {event['output']}</tool>"
```

编辑器的小按钮显示当前事件可用的 dict key。点击 `tool_name` 会在光标处插入 `event["tool_name"]`；按钮不再生成
双花括号变量或替用户拼接字符串。

函数签名必须恰好是 `def output(event)`：不接受 `async def`、额外参数、默认参数、`*args` 或 `**kwargs`。脚本异常或
返回非字符串会终止本次运行，并经过普通运行错误边界返回；普通 API 和日志摘要不包含脚本 traceback 或事件正文。
这些脚本在受信任的服务进程内运行，不是 sandbox，也不支持为输出模式单独声明第三方依赖。

## 公共 dict 字段

每类 Agent 事件都包含以下字段；没有来源身份时，相关字符串为空。`data` 是 Python 对象，不会为了脚本先转成 JSON。

| key | Python 类型 | 含义 |
| --- | --- | --- |
| `event_type` | `str` | 当前事件类型，等于本页事件名 |
| `phase` | `str` | `start`、`end` 或 `error` 等语义阶段 |
| `sequence` | `int` | 本次请求内递增的规范化事件序号 |
| `timestamp` | `str` | RFC 3339 UTC 时间 |
| `namespace` | `str` | LangGraph namespace，根作用域为 `root` |
| `agent_name` | `str` | 事件所属 Agent 显示名 |
| `node` | `str` | 产生事件的模型、工具或图节点名 |
| `message` | `str` | 已规范化的主要文本；最常用的默认输出字段 |
| `data` | `object` | 对应完整语义事件的原始 Python 值，具体类型见下表 |
| `source_type` | `str` | `agent`、`subagent`、`script` 或 `non_agent` |
| `workflow_node_id` | `str` | 画布 Workflow Node ID |
| `agent_profile_id` | `str` | Main Agent 配置 UUID |
| `subagent_profile_id` | `str` | Subagent 配置 UUID；非 Subagent 事件为空 |

## 各 Agent 事件 dict

下表中的“附加 key”与全部公共 key 一起出现在该事件的 `event` dict 中。除 `data` 外，附加字段均为 `str`。

| `event_type` | 附加 key | `data` 的 Python 值 |
| --- | --- | --- |
| `assistant_text` | `message_id` | 完整 text content block `dict`；媒体通知时为对应媒体 block `dict` |
| `reasoning` | `message_id` | 完整 reasoning content block `dict` |
| `tool_call` | `tool_name`, `tool_call_id`, `arguments` | 完整 tool-call content block `dict`；`arguments` 是字符串，结构化参数为紧凑 JSON 文本 |
| `tool_result` | `tool_name`, `tool_call_id`, `status`, `output` | 工具返回的 Python 值，可能是 `str`、`dict`、`list`、`tuple`、`ToolMessage` 或 `Command` 中的值；`output` 是规范化文本 |
| `tool_error` | `tool_name`, `tool_call_id`, `status`, `error_code` | 失败的工具事件或无效 tool-call content block `dict` |
| `subagent` | `subagent_name`, `tool_call_id`, `status` | Subagent lifecycle envelope `dict`；某些完成事件为 `None` |
| `custom` | `channel`, `data_json` | custom event 的原始 Python payload；`data_json` 是有界 JSON 文本 |
| `lifecycle` | `status`, `finish_reason`, `error_code` | lifecycle envelope `dict`，或 Shell 构造的状态 `dict` |

`assistant_text` 和 `reasoning` 的 token delta 会先缓冲。脚本只在完整语义 block 到达时执行一次，不能依赖每个 token
调用一次 `output()`。工具调用与可匹配的结果仍按同一来源和调用周期配对，并保持相邻输出。

## 读取 `data`

`data` 适合提取结构化值；代码必须按照所选事件实际类型访问。例如工具返回 dict 时：

```python
def output(event):
    result = event["data"]
    return str(result["answer"])
```

如只需要兼容不同 Provider 的公开文本，优先使用已规范化的 `message`、`arguments` 或 `output`。

## 过滤与保存结构

`allowlist` 只输出至少匹配一条映射的事件，`blocklist` 排除匹配项。映射对完整事件 dict 中的字符串化字段做精确匹配；
`data` 不作为过滤字段。可以使用公共字段名，也可以使用 `tool_result.status` 这样的事件限定字段名。

```json
{
  "name": "普通文本",
  "filter_mode": "blocklist",
  "filter_mappings": [],
  "event_outputs": {
    "assistant_text": {
      "enabled": true,
      "output_source": "def output(event):\n    return event[\"message\"]\n"
    },
    "reasoning": {
      "enabled": false,
      "output_source": "def output(event):\n    return event[\"message\"]\n"
    }
  }
}
```

真实 payload 必须包含 catalog 当前列出的全部八类事件；上例只节选两项。关闭事件会抑制该类普通投影，但不会隐藏顶层
HTTP/API 错误。流式与非流式响应消费同一组脚本结果，不会从最终 State 绕过输出模式读取原始 Agent 内容。
