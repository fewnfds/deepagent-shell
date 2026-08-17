# 日志中心与 Workflow 观测

## 日志中心

【系统 / 日志中心】合并两类记录：

- 系统日志：服务、配置和管理请求事件；
- Agent 运行日志：请求级错误摘要，以及 DEBUG 开启期间正常完成的请求摘要。

页面显示时间、来源、级别和摘要，并提供时间、来源、级别、关键词筛选以及批量删除。较大的条目和 DEBUG
异常日志通过操作列下载，不在页面正文展开。

系统日志按文件大小保留；运行日志按条数保留。删除运行日志或降低其保留条数时，对应的 DEBUG
文件一起删除。

## DEBUG 完整日志

DEBUG 开关位于日志中心，默认关闭，修改后立即生效。

开启后，每个正常完成的 Workflow Run 会新增一条 `INFO` 运行日志，并把完成状态、finish reason 和 token usage 写入
`data/logs/debug/`。运行异常仍在包装之前保存完整 Python exception chain 和 traceback。对应的 Agent 运行日志行会显示
下载按钮；关闭开关后正常请求不再生成运行日志或 DEBUG 文件，错误摘要仍会保留。已有文件仍可下载和删除。

DEBUG 文件可能包含请求内容、Provider 返回、凭据、宿主路径和自定义代码信息，大小也没有单文件上限。

## Workflow Debug

每次 Workflow 请求建立独立 thread，并由 LangGraph `AsyncSqliteSaver` 写入
`data/state/agent-shell.sqlite3`。当前 management API 提供有界运行索引、结构运行树和 checkpoint 摘要，用于定位失败的
Workflow、Agent、model 或 tool 节点；当前管理台没有 Workflow Debug 详情页面。日志中心的保留设置可以调整
Workflow Debug 运行索引上限，但它不替代 DEBUG traceback。

当前 checkpoint 尚未提供 Resume，但作为 Workflow Lifecycle 资源保留到用户显式清场；Workflow Debug retention 只影响运行索引和结构运行树，
不会隐式删除仍由 Lifecycle 引用的 parent/child thread checkpoint。

## LangSmith

LangSmith 是可选的外部 trace 服务，可查看 prompt、模型输出、工具调用和更完整的 LangChain/LangGraph 运行结构。
本地 DEBUG 日志不依赖 LangSmith；两者可以分别开启。
