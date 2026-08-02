# 异常重试

【异常重试】为模型调用选择一个有限 retry owner。它不要求模型调用 Finish 工具，不接管 response
format、tool choice、并行工具调用、Agent 路由或正常终止。Primary 引用后默认继承给同步 Subagent，
Subagent 覆写可以替换或关闭。

## 两种互斥方案

### Provider 原生重试（偏保守）

组件把 `max_retries` 写入当前 Provider integration；Google GenAI 使用对应的 `retries` 参数。重试由
integration 或底层 SDK 管理，不装配模型重试 Middleware。不同 Provider 对具体异常的支持可能不同。

### LangChain Middleware 重试（更可控）

组件先把 Provider 原生 retry 设为 0，再装配官方
`ModelRetryMiddleware(on_failure="error")`。因此始终只有一个 retry owner，不会产生 Provider 与
Middleware 的乘法重试。正常成功请求只调用模型一次，也不会增加提示词或工具 schema。

Middleware 模式可以选择：

- 网络连接或响应流中断；
- 请求或读取超时，包括 HTTP 408；
- 限流，包括 HTTP 429；
- Provider 服务端错误，包括 HTTP 5xx；
- 认证错误，包括 HTTP 401；该项默认关闭，只用于已知会把临时上游故障错误报告为 401 的第三方网关。

真实凭据、权限、普通 4xx、内容审核、模型拒答、`finish_reason=length` 和未知程序错误默认不重试。
Middleware 使用 LangChain 官方退避与 jitter，耗尽后重新抛出异常，由 Shell 的 Provider 错误边界生成
稳定、脱敏的运行错误，不生成伪 AIMessage。

## 公共选项

`max_retries` 是首次失败后的额外 Provider 请求次数，范围 0–10。两种方案共用这一含义。

“强制使用完整、非流式模型响应”同时设置通用 `disable_streaming` 与 Provider 的 `streaming=false`。
它不禁止一次回复内的并行工具调用，也不增加模型 token，但会增加首字等待时间。开启后，失败 attempt
可以在任何模型正文公开前重试；关闭后，流式调用中途断开时，已经发送给客户端的片段无法撤回。

## 不在本组件中的能力

- 不根据回复正文猜测截断或“不健康”；完整 AIMessage 不会被 Shell 二次审判；
- 不提供 Provider 与 Middleware 混合模式，避免最坏请求数相乘；
- 不内置 `ModelFallbackMiddleware`。需要备用模型的用户可以通过【自定义 Middleware】自行构造官方
  Middleware，并自行负责备用模型、凭据、费用与输出差异。

非流式、重试和备用模型都可能增加延迟或 Provider 费用。本组件只提高明确瞬时异常下的调用韧性，不
保证永久故障、错误配置或已公开流式片段能够自动恢复。
