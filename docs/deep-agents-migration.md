# Deep Agents runtime 基线

Agent Shell 使用锁定版本的 `deepagents.create_deep_agent()` 构造 Primary Agent 和每个同步 Subagent。

## 责任边界

Agent Shell 负责：

- 解析模型、提示词、文件系统、Skill、工具、Middleware、输出和 Subagent 配置；
- 为一次请求建立配置与 credential 快照；
- 准备 backend、initial files、skills、tools、middleware 和 subagents 参数；
- 观察 v3 事件、记录脱敏诊断并生成 OpenAI-compatible 输出。

Deep Agents/LangGraph 负责模型循环、工具执行、同步委派、summarization、tool-call repair、适用模型的
prompt caching、状态合并、重试 Middleware 的执行和 graph 终止。

Agent Shell 不在 graph 创建后改写消息、判断下一步、替模型补造响应或改变终止条件。输出模式只投影
事件；拦截测试通过标准 Middleware 在 Provider 前短路。

## 装配

- Primary 必须有模型与输出模式；
- 同步 child 由同一 `create_deep_agent()` 构造，并作为 `CompiledSubAgent` 提供给父 Agent；
- 文件 workspace 的可见工具由最终 Filesystem/Skill 组合决定；配置的 workspace 在同一请求的代理树中
  共享，Skill namespace 按 Agent 只读隔离；
- Subagent 的能力按 inherit/replace/disabled 解析，模型必须保留，输出模式只属于 Primary；
- Prompt Preset 在各 Agent graph 启动前处理该 Agent 的输入。

升级 Deep Agents 时必须重新核对 constructor、Middleware 默认集合、SubAgentMiddleware 替换、backend
state transfer、v3 事件和 prompt caching 行为，并用最接近的行为测试确认。
