# 同步子代理（Synchronous Subagents）

本 block 保存同步 DeepAgents `SubAgentMiddleware` 的文本配置，不在这里定义具体
Subagent。Primary 引用该 block 即启用同步委派：

```json
{
  "name": "同步委派",
  "instruction_override": null,
  "task_description_override": null
}
```

- 该 block 不再保存重复的总开关；关闭委派时，在 Primary 装配中不引用它。
- 引用后，真实请求要求 Primary 至少有一个完整且已启用的 binding。
- 页面从服务端管理 catalog 取得当前默认文本。DeepAgents 0.7 的顶层 task
  system prompt 默认为空；`instruction_override=null` 时构造参数省略，不额外向 Primary 注入旧的
  委派使用 prose。非空文本作为完整自定义 task system prompt 传入。
- `task_description_override=null` 使用 0.7 当前精简的 task 工具说明；非空文本完整替换该说明。
  页面显示值与当前默认一致时保存 `null`。
- 每段最多 100,000 字符；自定义 task description 必须保留 `{available_agents}`，且这是唯一允许
  的单层花括号字段。JSON 等普通花括号写成 `{{` 和 `}}`；属性/索引、conversion、format spec
  和残缺花括号不能保存。普通 `instruction_override` 不经过这套 `str.format()` 字段替换。
- `task(description, subagent_type)` 的工具 schema 由 DeepAgents 固定，本页不展示或修改。

具体 binding 的名称、用途和可选覆写策略在【Agent / Primary Agent】维护；基础配置固定使用 binding
所在的当前 Primary，filesystem 在被 Primary 选择时固定继承，未选择时 Subagent 仍可运行但没有
文件工具。每次请求重新解析并构造；当前只支持 raw
synchronous Subagent，不缓存 graph，不支持 general-purpose 自动添加、异步、dynamic、
CompiledSubAgent 或递归委派。
