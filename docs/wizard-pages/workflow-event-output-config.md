# 事件输出

事件输出是可复用的 Workflow 组件。每个 Workflow 可绑定零或一个；不绑定时，Workflow-owned 的非 Agent 事件不会写入
OpenAI 响应。画布 Agent Node 产生的事件仍使用各 Main Agent 的[输出模式](output-mode-config.md)。

编辑方式与输出模式一致：每类事件提供启用开关、字段按钮和同步 Python `output(event)`。函数必须返回 `str`，脚本在一个
完整语义事件上执行一次。

```python
def output(event):
    state = event["data"]
    return str(state["shared_vars"]["answer"])
```

## 公共字段

所有 Workflow 事件都含有输出模式文档列出的公共字段：`event_type`、`phase`、`sequence`、`timestamp`、
`namespace`、`agent_name`、`node`、`message`、`data`、`source_type`、`workflow_node_id`、`agent_profile_id`、
`subagent_profile_id`。这里的 `event_type` 是下表的 Workflow v3 method 分类，而不是统一写成 `custom`。

## 各 Workflow 事件 dict

| `event_type` | 附加 key | `data` 的 Python 值 |
| --- | --- | --- |
| `custom` | `channel`, `data_json` | `get_stream_writer()` 或 v3 custom event 写出的原始 Python payload |
| `lifecycle` | `status`, `finish_reason`, `error_code` | Workflow/script lifecycle envelope `dict` |
| `values` | `channel`, `data_json` | LangGraph `values` 模式的完整 Workflow State，通常为 `dict` |
| `updates` | `channel`, `data_json` | LangGraph `updates` 模式的 node-to-update `dict`，值可能继续包含消息或 `Command` 等 Python 对象 |
| `tasks` | `channel`, `data_json` | LangGraph task 事件的 Python payload，通常为 task 描述 `dict` 或集合 |
| `checkpoints` | `channel`, `data_json` | checkpoint 事件的 Python payload，通常为 `dict` |
| `input` | `channel`, `data_json` | 图输入事件的 Python payload，通常为输入 State `dict` |
| `input.requested` | `channel`, `data_json` | 请求外部输入/中断相关的 Python payload |
| `debug` | `channel`, `data_json` | LangGraph debug payload，通常为 `dict` |
| `other` | `channel`, `data_json` | 当前未归入上述 method 的原始 payload；`channel` 保留原 method 名 |

`channel` 对已知 State 类事件等于事件 method；`data_json` 是用于显示和简单拼接的有界 JSON 文本。要访问完整 State、消息
对象、`Command` 或其他 Python 值，应使用 `event["data"]`。这些对象来自锁定 LangChain/LangGraph 版本的 v3 语义 payload，
不保证本身 JSON-compatible；本页外层 `event` dict 和字段名才是 Agent Shell 的稳定输出脚本 contract。

脚本异常、返回非字符串和签名不符的处理边界与[输出模式](output-mode-config.md)相同。组件源码在受信任服务进程中执行，
不是 sandbox。
