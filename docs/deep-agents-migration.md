# Deep Agents runtime 基线

Agent Shell 使用锁定版本的 `deepagents.create_deep_agent()` 构造 Primary Agent 和每个同步 Subagent。

## 责任边界

Agent Shell 负责：

- 解析模型、提示词、文件系统、Skill、工具、Middleware、输出和 Subagent 配置；
- 为一次请求建立配置与 credential 快照；
- 在 graph 构造前执行自动化 prepare，物化原生插件 Middleware，并管理请求级 lifecycle/complete；
- 准备 backend、initial files、skills、tools、middleware 和 subagents 参数；
- 观察 v3 事件、记录脱敏诊断并生成 OpenAI-compatible 输出。

Deep Agents/LangGraph 负责模型循环、工具执行、同步委派、summarization、tool-call repair、适用模型的
prompt caching、状态合并、重试 Middleware 的执行和 graph 终止。

Agent Shell 只在 graph 构造前准备 owner 基础消息，并在现有 deferred Subagent runnable invoke 时机械组合
profile 基础消息与 delegated input。插件的 model/tool 逻辑由 Shell 放入 constructor 的原生 Middleware
表达；Hook 执行归 LangChain。Shell 不判断下一步、替模型补造响应或改变终止条件。输出模式只投影事件；
拦截测试通过标准 Middleware 在 Provider 前短路。

## 装配

- Primary 必须有模型与输出模式；
- 同步 child 以持久 Subagent 实体定义；父级只保存实体 UUID 引用，Shell 把实体的 `name`、`description` 和
  唯一编译 runnable 投影为 `CompiledSubAgent`；diamond 和显式 cycle 复用同一 profile ID 对应的 runnable；
- 文件 workspace 在同一请求的代理树中共享；最终 Filesystem 与按 Agent 解析的 filesystem-permissions
  决定提示词、内置文件工具和 `permissions=`，Skill namespace 仍按 Agent 只读隔离；
- Subagent 的能力按 inherit/replace/disabled 解析，模型必须保留，输出模式只属于 Primary；
- 每个 Agent 身份的 automation bindings 独立物化原生 Middleware；Shell 不代理 Hook 返回值、排序或 wrap；
- Shell 额外拥有 prepare、request-local fixed-delay lifecycle 和 graph 外 complete，三者不是 LangChain Hook。

升级 Deep Agents 时必须重新核对 constructor、Middleware 默认集合、SubAgentMiddleware 替换、backend
state transfer、v3 事件和 prompt caching 行为，并用最接近的行为测试确认。
