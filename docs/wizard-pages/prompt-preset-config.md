# 提示词预设

Prompt Preset 在某个 Agent graph 启动前，对该消费者的客户端消息副本做一次确定性处理；它不是
LangChain Middleware，也不会在后续模型轮次重复运行。

```json
{
  "name": "worker startup",
  "tag_replacements": [
    {"tag": "|||requirement|||", "replacement": "Use the selected requirement."}
  ],
  "startup_messages": [
    {"role": "user", "content_template": "Complete this task: {task}", "name": null},
    {"role": "assistant", "content_template": "I will use the full context before responding.", "name": null}
  ]
}
```

标签替换只扫描本次 API 提交的原始 `role=user` 字符串正文。标签是非空单行普通文本，不是正则；
同一 Preset 内必须唯一，且任意两个标签不能互相包含。找不到标签时不处理，没有回退位置；空
`replacement` 明确表示删除标签。同一个标签在客户端正文中出现多次会以
`ambiguous_prompt_tag` 在 Provider 前拒绝，不猜测替换位置。所有标签基于原文一次计算，替换结果
不会再次扫描；未由当前 Preset 配置的其他文本保持原样。

标签替换后，`startup_messages` 按保存顺序追加到同一 Agent 输入。角色只允许 `user` 与
`assistant`，可选 `name` 直接作为 LangChain 消息 name。管理 catalog 会列出当前可用模板变量；
Primary 与 Context Worker 的变量范围不同，保存与装配校验以服务端报告为准。启用 Context Worker
委派的 Primary Preset 必须使用 `{available_workers}`，有效 Worker Preset 必须使用 `{task}`。

Primary 与每次 Context Worker 调用各自选择自己的 Prompt Preset。Worker 可对同一个客户端标签使用
不同替换、删除或保持未配置；框架不内置业务标签、角色或流程。未选择 Preset 时不替换客户端正文，
也不追加启动消息。DeepAgents Subagent 不经过这套 Shell 输入预处理。
