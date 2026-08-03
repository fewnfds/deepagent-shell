# 拦截测试

拦截测试用于查看首个 Provider 调用前的最终 `ModelRequest`。在【系统 / 系统配置】开启后，正常的
Agent 装配和 Middleware 仍会执行，但最终测试 Middleware 会保存请求并返回固定回答，不访问 Provider。

记录包含原始 API 请求、最终 messages、工具 schema、tool choice、response format、模型类型和安全的
model settings。它只覆盖首次 model call，不执行后续工具循环。

在【系统 / 日志中心】筛选“拦截记录”查看或下载。记录可能包含完整用户消息和最终提示词，只能通过
management scope 访问；其中不保存 Authorization、Provider credential、客户端地址或 traceback。

拦截开关和保存上限都持久化。完成检查后应关闭开关，日志中心会在开启期间持续显示警告。
