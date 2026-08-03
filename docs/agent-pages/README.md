# Agent 配置

- [Primary Agent](primary-agents.md)：选择组件并定义公开 model ID。
- [Subagent](subagents.md)：为同步子代理定义继承、替换、关闭和子绑定。
- [术语](terminology.md)：管理台常用中英文名称。

Primary 与 Subagent 都通过 UUID 引用组件。模型与输出模式是 Primary 必选项；Subagent 必须保留一个
有效模型，输出模式只属于顶层 Primary，文件系统在同一次请求的整个代理树中共享。
