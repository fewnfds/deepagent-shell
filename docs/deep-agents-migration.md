# Deep Agents 升级基线

本项目从 `agent-shell` 升级而来。管理台、FastAPI/OpenAI-compatible 接口、SQLite 配置、Provider、
自定义 Tool/Middleware、输出投影、鉴权、日志和发行流程属于优先复用范围；Agent 构造与能力装配改用
`deepagents.create_deep_agent()`。

## 与 `create_agent()` 的区别

LangChain `create_agent()` 是最小且高度可配置的 harness，能力主要由调用方通过 Middleware 逐项组合。
Deep Agents 是建立在 LangChain Agent 和 LangGraph runtime 之上的预装 harness，面向长任务提供文件系统、
上下文管理和委派能力。

主 Agent 的 Deep Agents 默认栈包括：

1. `FilesystemMiddleware`；
2. `SubAgentMiddleware`；
3. `SummarizationMiddleware`；
4. `PatchToolCallsMiddleware`；
5. 适用 Provider 的 prompt caching middleware。

传入 `skills`、async subagents、`memory` 或 `interrupt_on` 时还会加入相应能力。`middleware=` 不是替换
整套默认栈：与默认 middleware `.name` 相同的实例原位替换该默认项，其他实例插入默认栈的指定位置。
替换 `FilesystemMiddleware` 时必须显式传入完整 backend/permissions 配置，不能假设继承构造器参数。

## 本项目的装配边界

- Primary、同步 Subagent 和 Context Worker 最终都必须通过 `create_deep_agent()` 构造；不得保留另一条
  `create_agent()` 产品内核路径。
- “未选择不装配”只适用于本项目数据库中的用户资源；不能用于描述 Deep Agents 的默认 middleware。
- 原项目的 Todo、Filesystem、Skill 和 Subagent 配置需要逐项映射到 Deep Agents 原生参数或默认
  middleware 覆写，避免重复注册工具或堆叠同类 middleware。
- API、持久化、Provider 初始化、输出事件、安全边界和 UI 可独立复用；涉及 graph state、stream event、
  tool namespace、subagent 继承或 middleware 顺序的代码必须重新核对。
- 迁移期文档描述目标架构。代码迁入后，源码与行为测试重新成为最终事实来源。

## 官方资料

- [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview)
- [Customize Deep Agents](https://docs.langchain.com/oss/python/deepagents/customization)
- [LangChain Agents](https://docs.langchain.com/oss/python/langchain/agents)
- [Build a deep agent from scratch](https://docs.langchain.com/oss/python/langchain/deep-agent-from-scratch)
