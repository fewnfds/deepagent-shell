# Context Worker

Context Worker Profile 保存一个可复用的 Worker 装配方案。Primary 只通过 binding 引用 Profile；Profile
本身不绑定某个 Primary，也不定义业务角色。

```json
{
  "name": "independent worker",
  "include_client_messages": true,
  "capability_overrides": [
    {"type": "model", "mode": "replace", "block_id": "UUID"},
    {"type": "custom-tool", "mode": "disabled", "block_id": ""}
  ]
}
```

可覆写能力使用三种界面模式：未保存显式项表示继承 Primary，`replace` 引用同类型现有组件，
`disabled` 移除可选能力。model 只能继承或替换。哪些组件可覆写以及固定继承、移除、顶层专属或受保护
策略由服务端 capability manifest 决定；前端不维护第二份规则。

`include_client_messages=true` 时，Worker 从本次请求的完整冻结客户端消息副本开始；false 时不携带该
副本。两种情况都只追加 Worker 自己的 Prompt Preset，不继承 Primary 已经产生的 AIMessage、
ToolMessage 或内部决策过程。

Primary 的每条 `workers[]` binding 保存唯一名称、告诉 Primary 何时调用的 description 和必填
`worker_profile_id`。只有 Primary 同时装配 Context Worker 委派组件时才创建 `run_worker` Tool；选择
委派能力后必须至少有一个有效 binding。Worker Profile 的保存、引用与删除保护均由后端 UUID contract
负责。DeepAgents Subagent 页面与运行行为保持不变。
