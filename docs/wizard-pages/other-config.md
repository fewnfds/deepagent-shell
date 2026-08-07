# 其他配置

其他配置用于统一管理 Deep Agents 启动时默认装配的两个 Middleware：

- `SummarizationMiddleware`：在上下文达到阈值时压缩较旧消息，并可在压缩前截断较大的历史工具参数；
- Anthropic `Prompt caching middleware`：为 Anthropic 请求添加 prompt cache 控制块。

阈值选择“自动”时，运行时保留 Deep Agents 0.7.5 的模型感知默认值：有模型上下文 profile 时按上下文比例计算，
没有 profile 时使用固定 token/消息数。也可以显式选择 fraction、tokens 或 messages 并填写值。

摘要 Prompt 编辑器默认显示 Deep Agents 内置 Prompt；未修改时仍使用该默认值，点击“还原默认文本”可撤销覆写。
“工具参数截断后的替代文本”是在历史工具参数超过长度阈值时，用来替代被删除内容的文本，不是摘要 Prompt。

Prompt caching 的 TTL 支持 `5m` 和 `1h`，并可设置启用缓存前的最少消息数。它按 `anthropic` Provider 适配器识别：
非 Anthropic Provider 仍会装配该中间件，但中间件会自动跳过请求，不会修改消息。
