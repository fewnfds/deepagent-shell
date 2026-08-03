# 术语

| 界面名称 | 含义 |
| --- | --- |
| Primary Agent | `/v1/models` 中公开、直接接收客户端请求的 Agent |
| Subagent | 具有组件配置名、路由名、说明和 settings，可由父 Agent 通过 `task` 同步调用的实体 |
| 组件 | 可被 Agent 按 UUID 引用的能力配置 |
| Subagent 引用 | 父 Agent 保存的 `subagent_id`，运行时投影实体的路由名、说明和 runnable |
| Skill | 含 `SKILL.md` 的按需说明目录 |
| 自定义工具 | 从 Python `@tool` 资源物化的 LangChain Tool |
| 自定义 Middleware | 用户提供的 LangChain Middleware 构造源码 |
| 输出模式 | v3 运行事件到响应文本的投影规则 |
| 历史会话 | 按 `X-Agent-Session-ID` 聚合的只读运行记录 |
