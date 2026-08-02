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
每条 binding 的 child graph 都由 `create_deep_agent()` 构造，再以官方 `CompiledSubAgent` 交给父 Agent
的 `subagents=` 参数。Agent Shell 全局关闭隐式 `general-purpose`；Primary 与每个 Subagent 覆写分别保存
自己的命名 bindings，空 catalog 没有 `task`。Subagent 可引用自身或其他覆写形成循环，调用和终止仍由
Deep Agents/LangGraph 管理。

项目 Filesystem 不进入 Subagent 覆写策略。同一次请求只装配一个 workspace，Primary 与所有同步 child
双向共享虚拟 `files` state、初始虚拟文件和 mapped routes；未选择项目 Filesystem 时也共享上游默认
StateBackend，但只暴露 `read_file`。项目 Skills、模型、工具和其他允许继承的能力仍按 Subagent 覆写
策略解析；Skill 选择不得
创建第二套普通 workspace，而是在共享普通 workspace 上为 child 叠加只暴露其最终选中 Skill 的只读
`/skills/` overlay；未选路径返回 not found。Prompt Preset 也可继承、替换或关闭，并通过 child 原生
`before_agent` Middleware 处理 binding 选择的冻结客户端消息，随后保留委派 task。当前不支持异步或
dynamic Subagent。
