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

Deep Agents 在没有显式 `subagents=` 时会自动添加 `general-purpose` 和 `task`。Agent Shell 在每个实际
model Provider 的 Harness Profile 中关闭该默认项，只向模型暴露用户明确保存的命名 Subagent。Primary
和每个 Subagent 覆写都拥有自己的 `subagents[]`；列表为空时该 Agent 没有 `task`，列表非空时仍由官方
`SubAgentMiddleware` 生成 `task`。递归只能来自显式自引用或循环引用，仍受 LangGraph recursion limit
约束。

同步 Subagent block 保存 `instruction_override` 和 `task_description_override`。Primary 使用自己的选择；
命名 child 可继承本次请求 Primary 的选择、替换为另一配置或关闭。最终拥有命名 catalog 的 Agent 才应用
自己的 instruction，并在 task description 非空时通过同名 `SubAgentMiddleware` 替换进入官方装配链。
真实 `subagents=`、工具参数 schema 和执行行为仍由 Deep Agents 管理，空值使用上游默认说明。

## 本项目的装配边界

- Primary 和同步 Subagent 的最终 graph 必须通过 `create_deep_agent()` 构造；Shell 在构造后只观察事件、记录诊断
  和投影公开输出，不接管模型循环、工具执行、重试或终止。
- 同步 child 使用当前 Primary 的有效能力解析结果和可选覆写，再以官方 `CompiledSubAgent` 进入父 Agent
  的原生 `subagents=` 装配链；child catalog 只来自目标覆写自己的 `subagents[]`，不隐式复制父 catalog。
  自引用和循环引用通过请求级有限 graph registry 与延迟 runnable 解析，不展开无限构造。
- Filesystem 不属于 Subagent 可覆写能力；同一次请求的 Primary 与所有同步 child 通过上游 `task` state
  transfer 双向共享完整虚拟 `files` state、一次性初始文件和 mapped routes。Skill 仍可按 Agent 选择
  提示与 sources；每个 Agent 只读 `/skills/` overlay 只暴露其最终选中的 Skill，但不得据此创建第二套
  普通 workspace。
- 不新增 Agent Group、外层 supervisor、调度循环、graph cache、checkpointer、store、memory 平台或通用 migration
  框架；API、持久化、Provider、输出观察和 UI 可以继续复用。

## Subagent 输入与 Prompt Caching

child 的最终 Prompt Preset 是冻结客户端消息与 Startup conversation 的唯一输入门禁。选择或继承到
Preset 时，child 通过 LangChain 原生 node-style `before_agent` Middleware 在自己的 graph 启动时重建
消息：先处理本次请求冻结的客户端消息，再追加 Preset Startup conversation，最后保留 Deep Agents
传入的 delegated task。最终没有 Preset 时不装配该 Middleware，child 只接收 delegated task。该逻辑不
包裹 `CompiledSubAgent` runnable，也不修改 Deep Agents 源码；每次委派都得到 fresh child state。

普通 Subagent 可以自由替换或关闭允许覆写的 model、system prompt、tools、Skill、Middleware、Prompt
Preset、response format 和 retry；自由装配是产品基线，不承诺 Primary 与 child 之间的 Prompt Caching。
用户需要尽量共享长前缀时，可以手工让 Primary/child 的 model、最终 system prompt、冻结客户端消息处理
结果、按相同顺序生成的 tool schema、response schema 与相关 model settings 保持一致，只用不同 Preset
末尾的 Startup conversation 区分身份。即使如此，缓存是否命中、最小 token 门槛、缓存范围和计费仍由
具体 Provider/model 决定；项目不把命中作为运行保证，也不增加缓存模式或自动对齐校验。

工具不能被假定为“位于消息之后”的无关尾部。Provider 的缓存 wire 和序列化顺序不是本项目 contract；
如果最终 `task` schema、其他工具的名称/description/参数结构或顺序不同，完整请求前缀可能在工具处就分叉。
需要让 Primary 与 Subagent 的 `task` schema 相同时，为两者显式配置相同的命名 catalog（名称、说明及顺序
一致），并让同一 `task_description_override` 在两侧展开为相同文本。不同 Agent 的 catalog 可以使用同一个
模型可见 binding 名称，例如都叫 `worker`；名称只要求在各自 catalog 内唯一。Agent Shell 继续把这些 catalog 交给
官方 `SubAgentMiddleware`，不自定义工具参数 schema；实际对齐面仍应以最终 `ModelRequest` 为准，不能只
比较工具名。

## 官方资料

- [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview)
- [Customize Deep Agents](https://docs.langchain.com/oss/python/deepagents/customization)
- [LangChain Agents](https://docs.langchain.com/oss/python/langchain/agents)
- [Build a deep agent from scratch](https://docs.langchain.com/oss/python/langchain/deep-agent-from-scratch)
