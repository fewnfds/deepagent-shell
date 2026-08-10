# 上下文摘要

上下文摘要组件单独配置官方 `SummarizationMiddleware`：在上下文达到阈值时压缩较旧消息，并可在压缩前截断较大的
历史工具参数。Main Agent 与 Subagent 可以分别选择、替换或关闭该组件。

阈值选择“自动”时，运行时保留 Deep Agents 0.7.5 的模型感知默认值：有模型上下文 profile 时按上下文比例计算，
没有 profile 时使用固定 token/消息数。也可以显式选择 fraction、tokens 或 messages 并填写值。

摘要 Prompt 编辑器默认显示 Deep Agents 内置 Prompt；未修改时仍使用该默认值，点击“还原默认文本”可撤销覆写。
“工具参数截断后的替代文本”是在历史工具参数超过长度阈值时，用来替代被删除内容的文本，不是摘要 Prompt。
