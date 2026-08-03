# 提示词预设

Prompt Preset 在 Agent graph 启动前处理该 Agent 的输入：

```json
{
  "name": "startup",
  "tag_replacements": [{"tag": "|||requirement|||", "replacement": "Use this requirement."}],
  "startup_messages": [{"role": "user", "content_template": "Complete: {task}", "name": null}]
}
```

- 标签是非空单行普通文本，同一 Preset 内不能重复、互相包含或在客户端原文中出现多次；
- 替换只扫描原始 user 文本一次，空 replacement 表示删除标签；
- 启动消息按顺序追加，role 只允许 `user` 或 `assistant`；
- `{task}` 只在 Subagent 中可用；Primary 的 Preset 不能使用模板变量；
- 组件至少包含一条标签替换或启动消息。

Subagent 可以继承、替换或关闭 Prompt Preset。处理完成后 delegated task 保留在 child 输入末尾。
