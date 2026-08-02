# Context Worker 委派

本组件向 Primary 提供标准 LangChain Tool：`run_worker(worker, task)`。它只配置工具 schema 说明和
请求级限制，不保存具体 Worker；可用 Worker 在 Primary Agent 页面绑定。

```json
{
  "name": "worker delegation",
  "tool_description": "Delegate one self-contained task to a configured Context Worker and return its final result.",
  "worker_parameter_description": "The configured Context Worker that should perform the task.",
  "task_parameter_description": "A complete and specific task for the selected Context Worker.",
  "max_worker_calls_per_request": 16,
  "max_parallel_workers": 4
}
```

`worker` 参数的 enum 由当前 Primary 已绑定的 Worker 名称生成；`task` 是本次调用的明确任务。模型可在
同一个响应中发出多个 Tool Call，LangChain ToolNode 按正常工具语义并行执行，Primary 等待各个结果
作为独立 ToolMessage 返回后继续下一轮。DeepAgent Shell 不实现第二套 supervisor loop。

每次调用会从请求快照构造一个完整 `create_agent()` Worker graph。Worker 得到冻结客户端消息副本
（若 Worker Profile 启用）与自己的 Prompt Preset，不继承 Primary 的 AI/Tool 调用历史。需要传递
Primary 运行中产生的内容时，应写进 `task`，或通过双方明确装配的共享文件路径传递。

请求总调用上限为 1–64，并行上限为 1–16，且并行上限不能大于总调用上限。Worker 侧保留受保护的
`run_worker` schema，但递归调用会返回稳定拒绝结果。DeepAgents 同步 Subagent 是独立能力，不受本
组件影响。Context Worker 的 Deep Agents 迁移本阶段暂停；后续是否由同步 Subagent 取代另行决定。
