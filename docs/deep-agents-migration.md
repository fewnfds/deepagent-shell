# Deep Agents runtime 基线

Agent Shell 使用锁定版本的 `deepagents.create_deep_agent()` 构造 Main Agent。直接 Subagent 使用 Deep Agents 官方
dictionary-based `SubAgent` 配置；Shell 不再为 child 编译自定义 graph。

## 责任边界

Agent Shell 负责解析 Workflow、Main Agent、组件、直接 Subagent 和 Provider secret 快照，准备 constructor 参数，
加载自定义 Middleware 包，编译外层 `START -> agent -> END` StateGraph，并观察 v3 事件生成
OpenAI-compatible 输出。

Deep Agents/LangGraph 负责模型循环、工具执行、同步委派、summarization、tool-call repair、prompt caching、
state reducer、Middleware Hook、`Command`、错误传播和 graph 终止。

用户 Python 扩展只返回官方 `AgentMiddleware`。Shell 不执行 prepare、fixed-delay lifecycle 或 complete，不建立第二套
model/tool/agent Hook。需要 checkpoint 的业务数据通过官方 state update 写入 `AgentShellState`。

## 装配

- Workflow 名称是公开 model ID；首版 Workflow 引用一个 Main Agent；
- Main Agent 必须有模型与输出模式；
- 只有 Main Agent 保存直接 Subagent UUID，Subagent contract 没有 child 引用；
- Subagent 能力按 inherit/replace/disabled 解析，并投影为官方字典 spec；
- 同一次请求共享 Deep Agents workspace/backend，权限与 Middleware 按 Agent 最终装配；
- `AgentShellState.shared_vars` 是公共 checkpointed 业务变量，Middleware 实例属性不是。

升级 Deep Agents 时重新核对 `create_deep_agent` constructor、dictionary SubAgent 字段、默认 Middleware、backend/state
transfer、StateGraph subgraph 组合和 v3 事件 namespace，并只为 Shell 自有转换保留行为测试。
