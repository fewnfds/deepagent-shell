# 同步子代理（Synchronous Subagents）

本 block 保存同步 Deep Agents 委派的附加指令，不在这里定义具体 Subagent：

```json
{
  "name": "同步委派",
  "instruction_override": null,
  "task_description_override": null
}
```

- 该 block 不保存重复的总开关；关闭委派时，Primary 不引用它。
- 引用后，真实请求要求 Primary 至少有一个完整且已启用的同步 binding。
- `instruction_override` 非空时追加到 Primary 的 system prompt；为空时不增加项目自定义指令。
- `task_description_override=null` 使用当前 Deep Agents 默认的 `task` 工具说明；非空文本通过官方
  `SubAgentMiddleware(task_description=...)` 同名替换完整覆盖说明，不改变工具参数 schema 或执行能力。
- 自定义 task description 必须保留 `{available_agents}`，且这是唯一允许的单层花括号字段。普通 JSON
  花括号写成 `{{` 和 `}}`。

每段文本最多 100,000 字符。具体 binding 的名称、用途和可选覆写策略在【Agent / Primary Agent】维护。
每条 binding 的 child graph 都由 `create_deep_agent()` 构造，再以官方 `CompiledSubAgent` 交给父 Agent
的 `subagents=` 参数。Agent Shell 全局关闭隐式 `general-purpose`；Primary 与每个 Subagent 覆写分别保存
自己的命名 bindings，空 catalog 没有 `task`。Subagent 可引用自身或其他覆写形成循环，调用和终止仍由
Deep Agents/LangGraph 管理。同一 Subagent block 的 task description 同时用于 Primary 和本次可达且
拥有 `task` 的 child；各 Agent 仍按自己的命名 catalog 展开 `{available_agents}`。

项目 Filesystem 不进入 Subagent 覆写策略。同一次请求只装配一个 workspace，Primary 与所有同步 child
双向共享虚拟 `files` state、初始虚拟文件和 mapped routes；未选择项目 Filesystem 时也共享上游默认
StateBackend，但只暴露 `read_file`。项目 Skills、模型、工具和其他允许继承的能力仍按 Subagent 覆写
策略解析；Skill 选择不得
创建第二套普通 workspace，而是在共享普通 workspace 上为 child 叠加只暴露其最终选中 Skill 的只读
`/skills/` overlay；未选路径返回 not found。Prompt Preset 也可继承、替换或关闭，并通过 child 原生
`before_agent` Middleware 处理冻结客户端消息，追加 Startup conversation，随后保留 delegated task；
最终没有 Prompt Preset 的 child 只接收 delegated task。当前不支持异步或 dynamic Subagent。
