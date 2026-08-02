# 提示词预设

Prompt Preset 在某个 Agent graph 启动前，对该消费者的客户端消息副本做一次确定性处理。Primary 在
构造 graph 输入时执行；Subagent 通过 LangChain 原生 node-style `before_agent` Middleware 执行。两者都
只处理一次，不会在后续模型轮次重复运行。

```json
{
  "name": "subagent startup",
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
Primary 可使用 `{agent_name}`；Subagent 可使用 `{agent_name}`、`{task}` 与 `{workspace}`。保存与装配
校验以服务端报告为准。

Primary 在 graph 启动前直接准备自己的输入。Subagent 的最终 Preset 可以继承 Primary、替换或关闭；
binding 的 `include_client_messages=true` 时，child 通过 LangChain 原生 node-style `before_agent`
Middleware 对本次请求冻结的原始客户端消息执行该 Preset，随后把 Deep Agents 的委派 task 保留在末尾。
为 `false` 时，Subagent Preset 只生成启动消息并排在 task 前。框架不内置业务标签、角色或流程；未选择
Preset 时不替换正文，也不追加启动消息。

该 Middleware 属于 child `create_deep_agent()` 的正常装配，不包裹官方 `CompiledSubAgent` runnable，
也不修改第三方源码。完整继承同一 Preset 并启用客户端消息有利于形成稳定消息前缀，但缓存还会受到
最终 model、system prompt、工具 schema/顺序、response schema、Provider 和 token 门槛影响，不保证命中。
