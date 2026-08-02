# Agent 页面

【Agent】包含三个子页面：

1. [Primary Agent](primary-agents.md)：选择十二类组件，并维护同步 Subagent 与 Context Worker binding。
2. [Subagent](subagents.md)：保存可复用的能力覆写策略。
3. [Context Worker](context-workers.md)：保存独立 Worker 的输入与能力装配方案。

历史会话属于运行观察功能，入口位于【系统 / 历史会话】；它不参与 Agent 装配或 memory。

[术语](terminology.md) 是独立一级只读页面。

三个装配页使用相同的能力选择卡和下拉框样式；Subagent 与 Context Worker 对允许覆写的能力提供
“继承”。配置名称用于阅读和选择，真实引用由服务端维护。
页面标题区提供新建和保存；删除配置统一前往【配置仓库】。
