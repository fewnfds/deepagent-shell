# Workflow Input Context

Workflow Input Context（WIC）是 Agent Shell 的核心上下文工程约定：它决定一次 Workflow 调用中的输入材料，如何在某个
Agent 真正启动前被选择、转换并写入该 Agent 的私有 `messages`。

WIC 不是画布 Node，也不是一类 capability 组件。当前实现是普通的 LangChain `AgentMiddleware`，通过官方
`before_agent` / `abefore_agent` hook 返回 Agent State update。Agent Shell 在 `examples/` 中提供一份可复制的实现，
每个使用者可以从它创建独立 Custom Middleware，再直接修改自己的上下文逻辑。

## 为什么需要 WIC

客户端提交的 `messages[]` 是本次请求的不可变事实，但 Agent Shell 不把整包消息自动写入 Workflow root State。画布上的
每个 Agent Node 都以自己的私有 Agent State 运行，默认输入 `messages` 为空；前序 Agent 的输出也不会自动变成后继 Agent
的对话历史。

这个边界使不同 Agent 可以针对同一请求获得不同材料：一个 Agent 可以读取完整原始任务，另一个只读取某个前序结果，
还可以加入共享 Filesystem 中的任务文件或把消息身份重新组织。WIC 是执行这些选择的唯一入口，而不是外围聊天历史、
自动累积机制或隐藏的 State 同步。

```text
客户端 messages[]
        │
        ▼
WorkflowRuntimeContext（不可变请求快照）
        │
        ├── 当前 Workflow State / 前序 agent_invocations
        ├── 当前 Agent 私有 State
        └── Workflow Filesystem backend
                    │
                    ▼
         WIC abefore_agent(...)
                    │
                    ▼
          当前 Agent 私有 messages
```

## 输入来源

WIC 可以在官方 Middleware hook 中组合以下数据：

- Main Agent：`runtime.context.messages` 中冻结的 OpenAI `system/user/assistant` 请求快照；
- Subagent：`state["messages"]` 中由 Deep Agents `task` 委派产生的私有消息，不自动附加根请求；
- 父 Workflow：`runtime.context.workflow_state`，包括前序 Agent 完成后写入的
  `agent_invocations[invocation_id]`；
- 当前身份：`runtime.context.workflow_node_id`、`agent_id` 与 `invocation_id`；
- 当前动态任务：Task Dispatcher worker 调用中的 `runtime.context.workflow_task`；普通 Agent 调用为空；
- 共享文件：工厂收到的 Workflow filesystem `backend`，只读取虚拟绝对路径；
- 当前 Agent State：hook 的 `state` 参数，以及其他 Middleware 声明的 State channel。

`runtime.context.messages` 始终只读。WIC 应复制需要的消息并通过返回值更新 State；消息 channel 使用
`Overwrite(convert_to_messages(...))`，避免与空初始值或其他 reducer 输入意外追加。

## Task Dispatcher worker

WIC 是任务材料的消费者，不是调度器。Task Dispatcher 先根据 Workflow State 生成任务，Shell 再通过 LangGraph `Send`
把每项任务作为私有 `workflow_task` 注入目标 Agent wrapper。worker 的 WIC 可以读取：

```python
task = runtime.context.workflow_task
task_id = task.get("task_id")
payload = task.get("payload", {})
```

同一份任务也存在当前 Agent 私有 State 的 `state["workflow_task"]`，但不写入 Workflow root State。任务完成后，父 State
的 `agent_invocations` 记录会携带 task identity，供下游汇总 Agent 的 WIC 选择。不要在 WIC 中扫描共享列表并用
`counting` 字段抢占任务；同一 super-step 的并行 worker 读取各自的 State 快照，不构成实时租约系统。

## 从内置示例创建

1. 打开【Agent 组件 / 自定义 Middleware】，新建配置。
2. 选择 `内置示例-workflow-input-context`。
3. 保存后编辑当前配置独占的 `main.py`。
4. 在 Main Agent 或 Subagent 的有序 `middleware_refs` 中选择该配置。

内置示例源码位于：

```text
examples/agent-components/custom-middleware/workflow-input-context/
```

它只是创建配置时的只读来源。保存后，系统会像其他 Custom Middleware 一样复制成配置独占的 Python 包；之后修改示例
不会改变已经创建的 WIC。用户模板可以同样命名，页面使用 `内置示例-` 前缀区分两个来源。

## 集中配置与变化函数

示例把通用功能集中在两个位置：

- `WIC_CONFIG`：配置附加文件和非顶部 system 转 user；
- `customize_context_messages(state, context)`：把 `context.messages` 复制为可编辑消息，并集中放置当前
  WIC 的选择、裁剪和重排逻辑；
- `build_workflow_input_context()`：集中执行附加文件和 system 转 user 等可选通用功能。

`WIC_CONFIG["attachments"]` 的每一项可以声明：

- `path`：首选 Workflow 虚拟文件；
- `fallback_paths`：按顺序尝试的备用文件；
- `literal`：所有文件缺失时的固定文本；
- `role`：追加消息的 `system`、`user` 或 `assistant` 身份；
- `max_chars`：追加前的字符上限；
- `stop_if_missing`：所有来源缺失时是否停止后续附件。

启用 `convert_non_leading_system_to_user` 后，只有消息列表开头连续的 system 消息保持 system；其余 system 消息转换为
user。附件和转换都位于同一个变化函数中，不需要时可以直接删除对应区块。

项目不定义更多 WIC 变种 schema。选择哪个前序 invocation、保留哪些原始消息、如何分配 role、是否加入文件以及如何截断，
都由当前 Middleware 的 Python 代码决定。多个 WIC 变种也只是多个普通 Middleware 配置。

## 顺序

WIC 没有专用装配槽位，也没有 Agent Shell 管理的固定相对顺序。Main Agent 和 Subagent 分别通过自己的
`middleware_refs` 决定 Custom Middleware 实例顺序。

LangChain 对 `before_*` hook 按 Middleware 列表正序执行；因此，如果多个 Middleware 都会改写 `messages`，后面的 hook
看到前面已经返回的 State。应在 Agent 配置中明确排列它们，而不是在 WIC 代码中寻找或调用其他 Middleware。

## 边界

- WIC 只构造当前 Agent invocation 的私有上下文，不修改客户端请求快照；
- Workflow root State 不保存整包输入，也不会自动累积成产品聊天历史；
- 前序 Agent 输出必须从 `agent_invocations` 显式选择，不能依赖 mapping 插入顺序；
- 同一画布节点再次执行会产生新的 invocation ID，WIC 应按节点身份或明确 ID 选择记录；
- Subagent 默认保留 delegated messages，是否加入根请求必须由该 Subagent 的 WIC 明确决定；
- 文件路径属于 Workflow 虚拟 Filesystem，不接受宿主绝对路径；
- Custom Middleware 是受信任的服务端 Python 代码，不在 sandbox 中运行。

LangChain 官方机制可参考 [Custom middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom) 和
[Runtime context](https://docs.langchain.com/oss/python/langchain/runtime#inside-middleware)。Python 包目录、依赖、复制和
运行边界见[文件化 Python 扩展](middleware-packages.md)。
