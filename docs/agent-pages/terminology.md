# 词库

| 界面名称 | 含义 |
| --- | --- |
| Workflow | `/v1/models` 中公开的 Workflow 入口；保存共享 Filesystem 和当前 Graph definition/layout |
| Main Agent | 完整的 Deep Agents 装配，可被 Workflow 画布的 Agent node 引用 |
| Endpoint | Node Catalog 声明的输入/输出控制流端点；当前 Edge 类型只有 normal |
| Edge | 从 source endpoint 到 target endpoint 的具体激活连接；不是 Vue Flow renderer 类型 |
| Subagent | 具有组件配置名、路由名、说明和 settings，可由父 Agent 通过 `task` 同步调用的实体 |
| 组件 | 可被 Agent 按 UUID 引用的能力配置 |
| Subagent 引用 | Main Agent 保存的 `subagent_id`，运行时投影为官方字典 SubAgent |
| Skill | 含 `SKILL.md` 的按需说明目录 |
| 自定义工具 | 从 Python `@tool` 资源物化的 LangChain Tool |
| 自定义 Middleware | 从本地包加载的官方 LangChain `AgentMiddleware` |
| 输出模式 | Main Agent 拥有的 v3 运行事件到响应文本投影规则；Workflow 按稳定 node/Agent 来源选择规则 |
| 历史会话 | 按 `X-Agent-Session-ID` 聚合的只读运行记录 |
