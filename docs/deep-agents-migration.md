# Deep Agents 升级基线

本项目从 `agent-shell` 升级而来。管理台、FastAPI/OpenAI-compatible 接口、SQLite 配置、Provider、
自定义 Tool/Middleware、输出投影、鉴权、日志和发行流程属于优先复用范围；本阶段只替换已经确认的
Agent 构造内核。

## 当前迁移状态

| 运行角色 | 当前构造入口 | 第一阶段状态 |
| --- | --- | --- |
| Primary | `deepagents.create_deep_agent()` | 已迁移 |
| 同步 Subagent | child `create_deep_agent()`，作为官方 `CompiledSubAgent` 交给 Primary | 已迁移 |
| Context Worker | 现有 `langchain.agents.create_agent()` + `run_worker` 薄工具边界 | 暂停迁移，后续是否改为同步 Subagent 另行决定 |

Context Worker 的 `create_agent()` 是当前明确的暂停边界，不代表项目保留第二套可选 Primary 内核，也不应在
新代码或说明中把它写成已经迁移。未来若取代它，应先验证冻结客户端多角色消息的窄 message adapter。

## 与 `create_agent()` 的区别

LangChain `create_agent()` 是最小且高度可配置的 harness，能力主要由调用方通过 Middleware 逐项组合。
Deep Agents 建立在 LangChain Agent 和 LangGraph runtime 之上，提供面向长任务的预装 harness：

- `FilesystemMiddleware`（默认 StateBackend 文件工具）；
- `SubAgentMiddleware`（有同步 Subagent 时提供 `task`）；
- `SummarizationMiddleware`；
- `PatchToolCallsMiddleware`；
- 适用 Provider 的 Prompt Caching middleware。

未传入项目 Filesystem block 只表示“不使用项目配置的 backend、映射和初始文件”，不会移除 Deep Agents 默认
Filesystem 工具。项目配置的同名 Filesystem/Skills Middleware 会按上游规则替换对应默认项；其他项目
Middleware 继续作为额外 Middleware 传入。Middleware 顺序不作为产品 contract，不增加顺序控制逻辑或测试。

Deep Agents 在没有显式同步 Subagent 时默认添加 `general-purpose` 和 `task`。本项目在 app 启动时为 bundled
Provider 注册官方 Harness Profile，关闭该自动 Subagent；只有 Primary 明确绑定同步 Subagent 时才把 child
graph 作为 `CompiledSubAgent` 传入，因此 child 不递归装配委派。

同步 Subagent block 当前只保存 `instruction_override`。非空内容追加到 Primary 的 system prompt；task 工具
schema 和 description 由 Deep Agents 管理，不再保存项目自定义的 `task_description_override`。

## 本项目的装配边界

- Primary 和同步 Subagent 的最终 graph 必须通过 `create_deep_agent()` 构造；Shell 在构造后只观察事件、记录诊断
  和投影公开输出，不接管模型循环、工具执行、重试或终止。
- 同步 child 使用当前 Primary 的有效能力解析结果和自己的模型，再以官方 `CompiledSubAgent` 进入 Primary 的
  原生 `subagents=` 装配链；当前 Primary 自身 bindings 不递归复制到 child。
- Context Worker 保持原 `create_agent()` 调用链，直到另一个 Goal 明确决定迁移方案。
- 不新增 Agent Group、外层 supervisor、调度循环、graph cache、checkpointer、store、memory 平台或通用 migration
  框架；API、持久化、Provider、输出观察和 UI 可以继续复用。

## 官方资料

- [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview)
- [Customize Deep Agents](https://docs.langchain.com/oss/python/deepagents/customization)
- [LangChain Agents](https://docs.langchain.com/oss/python/langchain/agents)
- [Build a deep agent from scratch](https://docs.langchain.com/oss/python/langchain/deep-agent-from-scratch)
