# 待办计划

选择本 block 时，builder 构造 LangChain `TodoListMiddleware`：

```json
{
  "name": "复杂任务计划",
  "system_prompt_override": null,
  "tool_description_override": null
}
```

当前锁定版本公开的可编辑 constructor 文本只有 `system_prompt` 和 `tool_description`。
页面通过服务端管理 catalog 始终显示与锁定 LangChain 版本一致的上游默认；未修改保存 `null`
并省略参数，修改后保存完整覆写。浏览器不保存另一份默认文本。每段最多 100,000
字符。

固定行为：

- 工具名为 `write_todos`；
- 输入是 `todos` 数组，每项包含 `content` 和 `pending|in_progress|completed` 状态；
- 每次调用替换整张列表；
- state 字段为 `todos`。

Primary 未选择时没有 Todo Middleware 或 `write_todos`。Subagent 可以继承、替换或关闭，且
拥有自己的 todos state。当前没有 checkpointer，Todo 不跨 API 请求恢复。

`TodoListMiddleware` 已作为独立一等组件接入，不再需要把它当作自定义 Middleware 模板。
