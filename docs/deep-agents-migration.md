# Deep Agents 升级基线

本项目从 `agent-shell` 升级而来。管理台、FastAPI/OpenAI-compatible 接口、SQLite 配置、Provider、
自定义 Tool/Middleware、输出投影、鉴权、日志和发行流程属于优先复用范围；本阶段只替换已经确认的
Agent 构造内核。

## 当前迁移状态

| 运行角色 | 当前构造入口 | 第一阶段状态 |
| --- | --- | --- |
| Primary | `deepagents.create_deep_agent()` | 已迁移 |
| 同步 Subagent | child `create_deep_agent()`，作为官方 `CompiledSubAgent` 交给 Primary | 已迁移 |

旧版的第二套 Agent 构造、独立 Profile、专用委派工具和事件已经删除。需要携带冻结客户端消息和独立
Prompt Preset 的委派统一由官方同步 Subagent 完成。

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

Deep Agents 在没有显式 `subagents=` 时默认添加 `general-purpose` 和 `task`。本项目保留这一上游基线：
Primary 配置命名 child 时，`task` 使用这些 `CompiledSubAgent`；child graph 未显式配置命名 child 时，仍可
使用上游 `general-purpose` 和 `task`，因此具备真实递归委派能力。递归是否发生由模型和提示词决定，最终仍
受 LangGraph recursion limit 约束；提示词建议不是强制禁止边界。

同步 Subagent block 当前只保存 `instruction_override`。非空内容追加到 Primary 的 system prompt；task 工具
schema 和 description 由 Deep Agents 管理，不再保存项目自定义的 `task_description_override`。

## 本项目的装配边界

- Primary 和同步 Subagent 的最终 graph 必须通过 `create_deep_agent()` 构造；Shell 在构造后只观察事件、记录诊断
  和投影公开输出，不接管模型循环、工具执行、重试或终止。
- 同步 child 使用当前 Primary 的有效能力解析结果和可选覆写，再以官方 `CompiledSubAgent` 进入 Primary 的
  原生 `subagents=` 装配链；Primary 的命名 bindings 不递归复制到 child，child 仍保留上游默认
  `general-purpose` 委派。
- 不新增 Agent Group、外层 supervisor、调度循环、graph cache、checkpointer、store、memory 平台或通用 migration
  框架；API、持久化、Provider、输出观察和 UI 可以继续复用。

## Subagent 输入与 Prompt Caching

binding 的 `include_client_messages` 决定 child 是否接收本次请求冻结的原始客户端消息。child 通过
LangChain 原生 node-style `before_agent` Middleware 在自己的 graph 启动时重建消息：先对可选客户端消息
执行该 child 最终 Prompt Preset，再追加 Preset 启动消息，最后保留 Deep Agents 传入的委派 task。该逻辑不
包裹 `CompiledSubAgent` runnable，也不修改 Deep Agents 源码；每次委派都得到 fresh child state。

普通 Subagent 可以自由替换或关闭允许覆写的 model、system prompt、tools、Skill、Middleware、Prompt
Preset、response format 和 retry；这种自由装配不承诺 Primary 与 child 之间的 Prompt Caching。需要尽量
共享长前缀时，应使用 `include_client_messages=true`，并让 child 完整继承同一 model、system prompt、
Prompt Preset、按相同顺序生成的 tool schema、response schema 与相关 model settings。即使如此，缓存是否
命中、最小 token 门槛、缓存范围和计费仍由具体 Provider/model 决定；项目不把命中作为运行保证。

工具不能被假定为“位于消息之后”的无关尾部。Provider 的缓存 wire 和序列化顺序不是本项目 contract；
如果最终 `task` schema、其他工具的名称/description/参数结构或顺序不同，完整请求前缀可能在工具处就分叉。
上游默认 `general-purpose` 能让 child 保留 `task` 能力，但它与 Primary 命名 Subagent 列表生成的 `task`
schema 仍可能不同，因此只能以拦截测试看到的最终 `ModelRequest` 判断实际对齐面，不能仅比较工具名。

## 官方资料

- [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview)
- [Customize Deep Agents](https://docs.langchain.com/oss/python/deepagents/customization)
- [LangChain Agents](https://docs.langchain.com/oss/python/langchain/agents)
- [Build a deep agent from scratch](https://docs.langchain.com/oss/python/langchain/deep-agent-from-scratch)
