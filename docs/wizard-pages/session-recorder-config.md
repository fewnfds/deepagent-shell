# Session Recorder

Session Recorder 是可选 Agent capability。Main Agent 选择后，Subagent 可按正常 capability 规则继承、替换或关闭。
它不创建对话隔离，也不由 `isolated` 模式自动启用。

Agent 完成后，Recorder 从最终 reduced `state["messages"]` 创建 OpenAI-style 副本。启用自定义变换时调用：

```python
def transform(messages, read_file, config, state, context):
    return messages
```

返回消息只写入新的 `agent_sessions[session_id]` record，不回写活动 `messages`。record 包含 Agent scope、ID、名称和
Workflow node ID。`python_requirements` 每行一个 PEP 508 requirement，依赖修改后重启生效。
