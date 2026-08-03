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
`assistant`，可选 `name` 直接作为 LangChain 消息 name。管理 catalog 只列出 `{task}`：它表示父 Agent
通过官方 `task` 工具传给 Subagent 的本次委派说明，只能用于 Subagent。Primary 使用的 Preset 不能包含
模板变量；同一 Preset 被装配给 Primary 时会在 Provider 前得到稳定校验错误。`{task}` 不是 Subagent
Preset 的必填项，静态正文和完整多角色消息仍可照常使用。

Primary 在 graph 启动前直接准备自己的输入。Subagent 的最终 Preset 可以继承 Primary、替换或关闭；
最终选择到 Preset 时，child 通过 LangChain 原生 node-style `before_agent` Middleware 对本次请求冻结的
客户端消息执行该 Preset，追加 Startup conversation，随后把 Deep Agents 的 delegated task 保留在末尾。
最终没有 Preset 时不装配该 Middleware，child 只接收 delegated task。框架不内置业务标签、角色或流程。

该 Middleware 属于 child `create_deep_agent()` 的正常装配，不包裹官方 `CompiledSubAgent` runnable，
也不修改第三方源码。不同 Agent 可以选择不同 Preset，只要用户让 tag replacements 的处理结果相同，
就能把较小的身份差异放到各自 Startup conversation 尾部；缓存还会受到最终 model、system prompt、
工具 schema/顺序、response schema、Provider 和 token 门槛影响，平台不保证命中，也不强制这种装配。
