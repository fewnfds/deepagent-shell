# Main Agent

Main Agent 是可复用的 Agent 装配，不再直接映射为 OpenAI `model`。Workflow 引用一个 Main Agent，并由
Workflow 名称进入 `/v1/models`。

每条 Main Agent 记录保存：

```json
{
  "name": "Research coordinator",
  "capability_refs": [
    {"type": "model", "block_id": "model-uuid"},
    {"type": "output-mode", "block_id": "output-uuid"}
  ],
  "subagents": [
    {"subagent_id": "subagent-uuid"}
  ]
}
```

`model` 与 `output-mode` 必选，其他 capability 可选。自定义 Middleware 包通过 `custom-middleware` 组件进入
`capability_refs`，没有 Agent 外的 prepare、周期循环或结束 Hook。

Main Agent 只有选择 Subagent capability 并引用至少一个 Subagent 实体时才获得 Deep Agents 官方 `task` 工具。
当前只支持一层同步 `Main -> Subagent`；多阶段与条件编排属于外层 Workflow。

删除仍被 Workflow 引用的 Main Agent 会被拒绝。先修改或删除相应 Workflow。
