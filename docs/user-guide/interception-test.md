# 拦截测试

【系统 / 系统配置】的拦截测试控制用于观察真实 Primary 在访问 Provider 前形成的最终
`ModelRequest`。开关是进程内全局状态，服务重启后恢复关闭；记录持久保存在 SQLite，不进入配置仓库。

## 执行方式

开启后，有效 Primary 请求仍走同一 `AgentBuilder`，先应用可选 Prompt Preset，再真实构造 selected
model、tools、Todo、filesystem/Skill、自定义 Middleware 与同步 Subagent 委派工具。
最终测试 Middleware：

1. 序列化 Provider 可见的 messages、tool schema、tool choice、response format、model 类型与
   安全 model settings；模型构造参数保留当前对象暴露的 Provider 原生字段名，不把
   `max_completion_tokens`、`max_tokens_to_sample` 等归并成通用名称；
2. 保存原始 API JSON 和最终请求 JSON；
3. 直接返回固定回答，不调用 Provider。

它覆盖首轮最终装配和首次 model call；Agent 工具循环与后续 model call 不在该测试范围内。

## 页面操作

系统配置页显示当前开关，并通过页面统一保存动作提交。开启时日志中心页面持续显示警告；管理 SSE
是否连通不影响已经生效的拦截开关。

来源筛选选择【拦截记录】即可集中查看。筛选 Card 的【批量删除】会删除后端全部匹配记录，不限于
当前已经加载的页面。

## 记录

事件摘要按拦截时间倒序排列；短记录展开后直接显示包含 request ID、Agent/model、原始请求和最终
ModelRequest 的完整 JSON，不再重复平铺其中字段。全文查询覆盖这些 metadata 和正文。

记录默认最多保留最近 20 条，可在事件页设置 1–10,000。每次新增会在同一事务中删除最旧超额
记录；保存较小上限后立即裁剪，调大不会恢复已删除数据。

短记录直接显示与下载文件同结构的 UTF-8 JSON；更长的记录通过操作菜单中的【下载完整条目】取得。
查看和下载不会改写数据库快照。

记录包含用户消息和完整最终提示词，只能通过 management scope 查看；它不保存 Authorization、
Provider credential、客户端地址、traceback 或 Provider 响应。

API 调用记录会同时记录客户端实际收到的固定拦截响应。两类记录通过 request ID 关联，但
含义不同，也都不会自动成为下一轮聊天历史。
