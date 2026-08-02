# 系统提示词

```json
{
  "name": "Concise assistant",
  "system_prompt": "Be concise and cite concrete evidence."
}
```

- `name` 与非空 `system_prompt` 必填；上限分别为 120 和 200,000 字符。
- Primary 选择后，正文直接传给 `create_deep_agent(system_prompt=...)`；未选择则省略该参数。
- LangChain Middleware 可以在后续 model-call 阶段追加或修改有效 SystemMessage。
- Subagent 可以继承、替换或关闭基础 system prompt。

本 block 始终保存用户原文，不保存 Middleware 产生的最终组合结果。可在【系统 / 系统配置】开启拦截测试，
再到日志中心观察最终请求。
