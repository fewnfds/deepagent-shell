# 日志中心与 Workflow 观测边界

## 当前日志中心

【系统 / 日志中心】只保留三类管理观测：

- 系统日志：服务启动/停止、配置变更、安全事件和失败的管理请求；
- 运行诊断：请求级、脱敏且有界的内部错误诊断；
- 拦截记录：Provider 边界测试产生的最终 ModelRequest（仅在拦截测试开启时写入）。

列表支持时间范围、来源、级别、全文搜索、页码分页、按当前筛选批量删除和大条目下载。系统日志按 MiB
限制；拦截记录与运行诊断按条数限制。降低上限会立即删除超出的旧记录。

日志中心不是 Workflow 执行历史，也不保存客户端完整消息、Provider 原始响应、traceback、工具参数/结果或
逐 token reasoning。拦截记录可能含有完整用户消息和最终提示词，只应在本地调试后及时删除或降低保存上限。

## Workflow Debug

每次 Workflow 请求建立独立 Debug thread 和 run identity。外层 Workflow 使用 LangGraph 官方
`AsyncSqliteSaver`，以 `durability="sync"` 在 super-step 边界写入 `data/state/agent-shell.sqlite3`。静态 Agent
子图继承父图 checkpointer；Shell 不实现第二套快照引擎。

管理接口只返回安全的结构信息：

- `GET /api/workflow-debug/runs`：有界运行索引；
- `GET /api/workflow-debug/runs/{thread_id}`：运行树与官方 checkpoint 摘要；
- `DELETE /api/workflow-debug/runs/{thread_id}`：删除索引并调用官方 `adelete_thread()`。

运行树包含 Workflow、Agent graph、model、tool 和 retriever 的父子身份与状态，不复制 prompt、工具参数/结果或
模型正文。Checkpoint 保存官方 Graph state，属于敏感实例数据；管理摘要只公开 checkpoint id、namespace、step、
channel 名称和 pending write 数量，不返回 state 值。

系统配置可以选择启用 LangSmith。LangSmith 是外部 trace 后端，通常会接收 prompt、模型输出、工具输入/输出等完整
追踪内容，只应在确认数据策略后启用；它不能替代本地系统日志、运行诊断或 checkpoint 数据库。

当前不提供 Resume、断线续跑、旧输入重发、面向用户的完整输入/输出回放或恢复 API。`messages_sha` 只作为 Debug
关联信息，不能触发执行。
