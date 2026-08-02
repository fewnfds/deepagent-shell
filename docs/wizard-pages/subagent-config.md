# 同步子代理（Synchronous Subagents）

本 block 保存同步 Deep Agents 委派的附加指令，不在这里定义具体 Subagent：

```json
{
  "name": "同步委派",
  "instruction_override": null
}
```

- 该 block 不保存重复的总开关；关闭委派时，Primary 不引用它。
- 引用后，真实请求要求 Primary 至少有一个完整且已启用的同步 binding。
- `instruction_override` 非空时追加到 Primary 的 system prompt；为空时不增加项目自定义指令。
- `task` 工具的 schema、description 和运行行为由 Deep Agents 原生 `SubAgentMiddleware` 管理；页面不再
  保存或修改 `task_description_override`。

每段文本最多 100,000 字符。具体 binding 的名称、用途和可选覆写策略在【Agent / Primary Agent】维护。
每条 binding 的 child graph 都由 `create_deep_agent()` 构造，再以官方 `CompiledSubAgent` 交给 Primary 的
`subagents=` 参数；child 不继续解析当前 Primary 的 bindings，因此不会递归委派。

项目 Filesystem block 被 Primary 选择时，child 继承该项目 Filesystem 配置；未选择时，Deep Agents 默认
StateBackend Filesystem 仍提供默认文件工具。项目 Skills、模型、工具和其他允许继承的能力按 Subagent
覆写策略解析。当前不支持异步或 dynamic Subagent。
