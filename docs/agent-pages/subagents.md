# Subagent

Subagent 页面保存可复用覆写策略。策略只有被 Primary 或另一个 Subagent 的 binding 引用时才生效：

```json
{
  "name": "researcher",
  "capability_overrides": [
    {"type": "system-prompt", "mode": "replace", "block_id": "UUID"},
    {"type": "custom-tool", "mode": "disabled", "block_id": ""}
  ],
  "subagents": []
}
```

- 未出现的能力继承 Primary；
- `replace` 必须引用同类型组件；
- `disabled` 不带 `block_id`；
- 模型可继承或替换，不能关闭；
- 文件系统由整棵请求代理树共享，不参与覆写；
- 输出模式只属于顶层 Primary；
- 其余可覆写组件支持继承、替换或关闭。

`subagents[]` 定义该 Subagent 自己可调用的命名子代理，字段与 Primary binding 相同。父级 bindings
不会自动复制给 child。

同一次请求中的 Primary 与同步 Subagent 共享普通 workspace 和 mapped routes。每个 Agent 根据自己的
最终 Skill 配置获得只读 `/skills/` 视图。请求结束后，内存 workspace 不保留；mapped directory 的
磁盘写入按本地文件系统持久化。
