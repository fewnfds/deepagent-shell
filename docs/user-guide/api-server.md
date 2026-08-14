# API Server

首页显示 API Server 状态、接入地址和配置告警，并提供启动、停止、API Key 和单次请求初始消息条数上限。
管理台 navbar 在所有页面显示运行状态。

## 接口

```http
GET /v1/models
Authorization: Bearer <API Key>
```

返回当前启用的 Workflow 名称。Main Agent 名称和内部 UUID 不属于 model ID。

```http
POST /v1/chat/completions
Authorization: Bearer <API Key>
Content-Type: application/json

{
  "model": "writing-workflow",
  "messages": [{"role": "user", "content": "Write a summary."}],
  "stream": false
}
```

请求按 Workflow name 捕获一次配置快照，从同一快照读取当前 Graph、共享 Filesystem 和画布 Agent 节点引用，再递归
构造该 Main Agent 的 Subagent、权限、Middleware、组件和 Provider secret view。构造完成后关闭请求配置快照，
运行中的图不再回读配置。

当前可执行 Node class 为 Start、Agent、条件路由和 End，Edge class 为 normal 与 branch；一张图可以包含多个 Agent node，并可串联、
fan-out、fan-in 或形成 LangGraph 支持的循环。画布 Start/End 直接映射 LangGraph 官方 `START/END`，normal edge 映射
`StateGraph.add_edge()`；条件路由脚本读取完整 Workflow State 和 Runtime Context，返回 State partial update 与一个或多个
分支 key；候选 key 直接由画布具名 Branch Edge 声明，并必须包含显式 `otherwise`，runtime 将其映射为
`Command(update=..., goto=[...])`。Start 不注入客户端消息。规范化后的 `messages[]` 保存在请求级不可变 Middleware context 中，只有已
装配的 `before_agent`/`abefore_agent` Middleware 决定如何切割并写入 Agent state。

`stream=false` 返回标准 `chat.completion` JSON。`stream=true` 返回 `chat.completion.chunk` SSE，并以
`data: [DONE]` 结束。两种模式都消费同一次 LangGraph v3 事件流，并按 Workflow node 对应 Main Agent 的
`output-mode` 的同步 Python `output(event)` 过滤和渲染；Workflow-owned 非 Agent 事件由 Workflow 可选绑定的事件输出
组件处理。脚本收到稳定 dict、必须返回字符串；两条路径都不会从最终 state 绕过输出策略读取原始 Agent 内容。

## 当前边界

- Workflow 只有一份当前图，没有 draft/published revision、发布审核或历史回滚；
- 每次请求是一次新的完整运行，并建立独立 Debug thread；外层 Workflow 使用官方持久 checkpointer，但不提供 resume；
- 当前不支持通用 conditional edge、动态 worker、Interrupt 或 Subworkflow；条件路由是唯一可编程路由 Node，多个 normal 出边和一次激活的多个 branch 目标会按 LangGraph super-step 语义并行执行；
- 图不完整、引用失效、Agent 装配失败或 Provider 失败时，本次请求直接返回错误；
- Workflow Debug 管理 API 提供有界运行索引、结构运行树和 checkpoint 摘要；日志中心展示系统事件、请求级
  错误诊断，并可按开关保存完整异常文件。当前不提供 Resume 或旧 Main Agent 直连兼容。

## API Key 与状态

API Key 是 write-only 设置，用于 `/v1/*`；管理密码用于管理台和 `/api/*`。清除 API Key 后推理 API 不可用。
API Server 启停不扫描未被 Workflow 引用的 Main Agent；完整 repository validation 只用于管理诊断，单次 Chat 请求
只解析所选 Workflow 的当前图和可达装配。

普通 API、DOM 和日志摘要不返回 Provider secret、Bearer token、宿主敏感路径、traceback 或 Provider 原始响应；
显式开启的本地 DEBUG 文件除外。
