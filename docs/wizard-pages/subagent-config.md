# 委派能力

该组件控制 Deep Agents 同步 `task` 委派的附加提示：

```json
{
  "name": "同步委派",
  "instruction_override": null,
  "task_description_override": null
}
```

- `instruction_override` 追加到当前 Agent 的 system prompt；
- `task_description_override` 完整覆写 `task` 工具说明，非空时必须保留 `{available_agents}`；
- 每段最多 100,000 字符；
- 具体 child 路由名、说明和能力策略在 Subagent 实体页面维护。

Agent 选择该组件且拥有至少一条有效 Subagent 实体引用时获得 `task`。每个唯一实体 graph 由
`create_deep_agent()` 构造并同步执行。Subagent 可继承、替换或关闭委派能力，并定义自己的下级实体引用。
