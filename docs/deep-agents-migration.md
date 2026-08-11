# Deep Agents runtime 基线

Agent Shell 使用锁定版本的 `deepagents.create_deep_agent()` 构造 Main Agent。直接 Subagent 使用 Deep Agents 官方
dictionary-based `SubAgent` 配置；Shell 不再为 child 编译自定义 graph。

## 责任边界

Agent Shell 保留 Main Agent、组件、直接 Subagent 和 Provider secret 的完整装配能力，并由
`deepagents.create_deep_agent()` 构造 compiled graph。当前 Workflow Agent node 引用完整 Main Agent，并把该 compiled
graph 直接装入 `START -> Agent -> END` 外层 StateGraph。

Deep Agents/LangGraph 负责模型循环、工具执行、同步委派、summarization、tool-call repair、prompt caching、
state reducer、Middleware Hook、`Command`、错误传播和 graph 终止。

用户 Python 扩展只返回官方 `AgentMiddleware`。Shell 不执行 prepare、fixed-delay lifecycle 或 complete，不建立第二套
model/tool/agent Hook。需要 checkpoint 的业务数据通过官方 state update 写入 `AgentShellState`。

## 装配

- Workflow 名称是公开 model ID；Main Agent 引用保存在 Graph Agent node config，不在 Workflow metadata 中；
- Main Agent 必须有模型与输出模式；
- 只有 Main Agent 保存直接 Subagent UUID，Subagent contract 没有 child 引用；
- Workflow 唯一选择共享 Filesystem；Main Agent/Subagent payload 不保存 Filesystem ref；
- Subagent 能力按 inherit/replace/disabled 解析，并投影为官方字典 spec；
- 同一次 Workflow 请求共享 Deep Agents workspace/backend，各 Main Agent/Subagent 的 `filesystem-permissions` 与文件
  tool override 按身份显式装配；
- Summarization 与 Prompt Caching 是两个独立 capability，每个身份显式物化自己的官方 middleware；
- `AgentShellState.shared_vars` 是公共 checkpointed 业务变量，Middleware 实例属性不是。

当前项目仍支持把 Workflow 的 mapped directories 接到 Deep Agents `FilesystemBackend`。LangChain 官方文档明确把
`FilesystemBackend` 列为不适合 Web server/HTTP API 的 backend；这是一条官方限制记录，不是 Shell 自己声称的安全保证。
如果未来要消除该限制，应按官方建议改用 `StateBackend`、`StoreBackend` 或 sandbox backend，并另立需求，不在本次 ctx 迁移中偷偷替换。

Canvas Start/End 只是 LangGraph 官方虚拟 `START/END`。客户端 `messages[]` 冻结在官方
`WorkflowRuntimeContext`，通过 root `context=` 传递；不会由 Start 注入或自动成为 Main Agent 活动消息。已装配的官方
`before_agent` Hook 从 `runtime.context.messages` 按 Agent 身份整理后产生 state update。

同步 Subagent 是 Agent 内部的官方 `SubAgentMiddleware` 能力，不与外层 Workflow 竞争调度职责。后续
AsyncSubAgent 使用 `create_deep_agent(subagents=[AsyncSubAgent(...)])` 的官方装配入口，并单独处理 `graph_id`、
Agent Protocol 地址、认证和后台 task state。

升级 Deep Agents 时重新核对 `create_deep_agent` constructor、dictionary SubAgent 字段、默认 Middleware、backend/state
transfer、StateGraph subgraph 组合和 v3 事件 namespace，并只为 Shell 自有转换保留行为测试。
