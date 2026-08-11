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

## 当前未提供 Workflow 历史

当前不收集 Workflow 内部节点树，不提供 session header、线性 Timeline、API 调用历史或 verbose diagnostics。
这些接口不属于当前产品 contract。

以下能力暂不提供，待 LangGraph 官方 thread/checkpoint 与并发运行契约明确后再单独设计：

- Workflow execution history 与 run tree；
- 多 Agent / 多脚本 node 的并发、重试、取消和关联关系；
- thread、checkpoint、resume 以及可恢复历史；
- 面向用户的完整输入/输出回放。

外部 LangSmith、Langfuse 或 OpenTelemetry sink（如果以后接入）只能作为可选 trace 后端，不能替代系统安全日志、
产品数据契约或 checkpoint/thread 存储。
