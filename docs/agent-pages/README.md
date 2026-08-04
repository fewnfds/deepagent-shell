# Agent 配置

- [Primary Agent](primary-agents.md)：选择组件并定义公开 model ID。
- [Subagent](subagents.md)：定义可复用的同步子代理实体、能力策略和下级引用。
- [术语](terminology.md)：管理台常用中英文名称。

Primary 通过 UUID 引用组件和 Subagent 实体；Subagent 实体通过 settings 引用能力覆写组件和下级实体。模型与输出模式是 Primary 必选项；Subagent 必须保留一个
有效模型，输出模式只属于顶层 Primary，文件系统在同一次请求的整个代理树中共享；文件系统权限按 Agent
继承、替换或关闭。
