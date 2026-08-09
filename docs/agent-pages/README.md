# Agent 配置

- [Main Agent](main-agents.md)：选择组件，作为 Workflow 的 Agent 节点装配。
- [Subagent](subagents.md)：定义可复用的同步子代理实体和能力策略；只允许 Main Agent 直接引用。
- [词库](terminology.md)：管理台常用中英文名称。

Main Agent 通过 UUID 引用组件和直接 Subagent 实体；Subagent settings 只保存能力覆写，不引用下级实体。模型与输出模式是 Main Agent 必选项；Subagent 必须保留一个
有效模型，输出模式只属于顶层 Main Agent，文件系统在同一次请求的整个代理树中共享；文件系统权限按 Agent
继承、替换或关闭。
