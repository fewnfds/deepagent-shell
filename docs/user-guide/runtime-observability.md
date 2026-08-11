# 日志中心与 Workflow 观测

## 日志中心

【系统 / 日志中心】合并三类记录：

- 系统日志：服务、配置和管理请求事件；
- Agent 运行日志：请求级错误摘要；
- 拦截记录：拦截测试捕获的 ModelRequest。

页面显示时间、来源、级别和摘要，并提供时间、来源、级别、关键词筛选以及批量删除。较大的条目和 DEBUG
异常日志通过操作列下载，不在页面正文展开。

系统日志按文件大小保留；运行日志和拦截记录按条数保留。删除运行日志或降低其保留条数时，对应的 DEBUG
文件一起删除。

## DEBUG 完整日志

DEBUG 开关位于日志中心，默认关闭，修改后立即生效。

开启后，Agent Shell 在包装运行异常之前保存完整 Python exception chain 和 traceback。文件写入
`data/logs/debug/`，不做字段白名单、脱敏或正文截断。对应的 Agent 运行日志行会显示下载按钮；关闭开关只停止
生成新文件，已有文件仍可下载和删除。

DEBUG 文件可能包含请求内容、Provider 返回、凭据、宿主路径和自定义代码信息，大小也没有单文件上限。

## Workflow Debug

每次 Workflow 请求建立独立 thread，并由 LangGraph `AsyncSqliteSaver` 写入
`data/state/agent-shell.sqlite3`。Workflow Debug 页面提供运行树和 checkpoint 摘要，用于定位失败的 Workflow、Agent、
model 或 tool 节点；它不替代 DEBUG traceback。

当前 checkpoint 只用于 Debug，不提供 Resume。

## LangSmith

LangSmith 是可选的外部 trace 服务，可查看 prompt、模型输出、工具调用和更完整的 LangChain/LangGraph 运行结构。
本地 DEBUG 日志不依赖 LangSmith；两者可以分别开启。
