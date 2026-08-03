# Subagent

Subagent 页面保存可复用的完整 Subagent 实体。实体只有被 Primary 或另一个 Subagent 引用时才参与运行：

```json
{
  "component_name": "web-researcher",
  "name": "researcher",
  "description": "Searches sources and returns evidence.",
  "settings": {
    "capability_overrides": [
      {"type": "system-prompt", "mode": "replace", "block_id": "UUID"},
      {"type": "custom-tool", "mode": "disabled", "block_id": ""}
    ],
    "subagents": [
      {"subagent_id": "UUID"}
    ]
  }
}
```

- `component_name` 是实体库内唯一的配置名；
- `name` 是 Deep Agents 使用的路由名，`description` 告诉父 Agent 何时委派；
- settings 中未出现的能力继承父 Agent；
- `replace` 必须引用同类型组件；
- `disabled` 不带 `block_id`；
- 模型可继承或替换，不能关闭；
- 文件系统由整棵请求代理树共享，不参与覆写；
- 输出模式只属于顶层 Primary；
- 其余可覆写组件支持继承、替换或关闭。

`settings.automation` 对事件工作流和定时工作流分别使用继承、替换或关闭。工作流不是组件，不放入
`capability_overrides`。

`settings.subagents[]` 是该 Subagent 自己可以调用的有序实体引用。父级引用不会自动复制给 child。同一个
实体在请求内无论从多少分支或显式循环到达，都只构造一个 Subagent graph；各次 `task` 调用仍分别执行。

同样地，一个实体在一次请求中只有一套自动化 owner、变量、Skill overlay 和定时任务；每次 `task` 调用前仍
分别执行一次该实体的 `subagent_before_invoke`，并使用新的独立消息副本。

同一次请求中的 Primary 与同步 Subagent 共享普通 workspace 和 mapped routes。每个 Agent 根据自己的
最终 Skill 配置获得只读 `/skills/` 视图。请求结束后，内存 workspace 不保留；mapped directory 的
磁盘写入按本地文件系统持久化。
