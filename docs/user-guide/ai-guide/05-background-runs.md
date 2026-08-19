# 使用后台 Run

后台 Run 是可选能力。普通线性 Workflow、同步 Subagent 和 Task Dispatcher 不需要使用它。

Agent Shell 提供单进程后台任务系统。它不是 LangGraph Graph Node，也不是 Deep Agents 的 SubagentMiddleware。它通过当前
Run 的官方 `Runtime.context.background_runs` 暴露给 Command Node、Task Dispatcher、Custom Tool、Middleware 和普通 Node：

```python
commands = runtime.context.background_runs
handle = await commands.start_agent(
    "<target Main Agent UUID>",
    operation_id="review:item-42",
    shared_vars={"item_id": "42"},
)
snapshot = await commands.check([handle.task_id])
```

可用命令只有 `start_agent()`、`start_workflow()`、`check()`、`list()` 和 `cancel()`。`start_workflow()` 的 target 必须是已
启用的 child Workflow；后台 Agent 使用自身有效 Filesystem。命令立即返回 handle，调用方自己决定如何轮询、
等待、重试、汇总或结束，并可把 handle 或 snapshot 写入 `background_tasks`。

## Lifecycle、Run 和 Thread

一次外部 `/v1/chat/completions` 请求创建一个 Lifecycle，并拥有一个 parent Run/thread。后台调用会在同一 Lifecycle 中创建
独立 child Run：

```text
Lifecycle
  parent Run
  background Agent Run
  background Workflow Run
```

每个 Run 都有独立的 `run_id`、`thread_id` 和 invocation 身份；后台 child 还带 `parent_run_id`、`launcher_id`、
`background_task_id` 和 `run_depth`。这些身份只能从官方 `Runtime.context` 读取，不能由脚本伪造，也不能把整个
Runtime/context/commands 写进 State 或 Store。

Lifecycle Store 保存本次请求的不可变输入、invocation artifact 和 task record；Workflow State 只保存路由所需的轻量引用。
独立后台 Run 不自动复制或合并父 Run 的 `messages`、State、checkpoint 或 Filesystem `files` channel。需要跨 Run 共享的
大材料应写入同一 Lifecycle 的受管 Filesystem 或官方 Store route，再由 child WIC/工具按引用读取。

后台 child 的输出默认静默消费，不自动混入 parent 的 OpenAI 响应。只有 parent 通过 `check()`/`list()` 取得事实并显式把
结果写入自己的 State、Store 或输出策略时，结果才成为 parent 后续可见材料。

## operation_id 与幂等

每次启动必须提供当前 caller Run 内稳定且不超过 128 字符的 `operation_id`。同一 Lifecycle、同一 caller Run、同一
operation ID 再次调用时返回原 task handle，不会重复派遣；若同 operation ID 改用另一个 target，返回冲突。该保证不跨
caller Run，也不跨尚未实现的 Resume；确实需要再次派遣时使用新的业务 operation ID。

不要把后台 Run 写成画布 Agent Node。后台 Agent 没有 `workflow_node_id`，但有实际 `agent_id`；后台 Workflow 也不会出现在
parent Graph 的 Node catalog 中。不要用后台系统替代 Deep Agents 官方同步 Subagent，也不要替代 Task Dispatcher 在同一请求内
通过 LangGraph `Send` 创建的动态 worker。

## Lifecycle 管理 API

Management API 只提供生命周期摘要和显式清场，不提供后台任务的通用外部启动 endpoint：

| 请求 | 作用 |
| --- | --- |
| `GET /api/workflow-lifecycles?page=1&page_size=10&query=` | 分页列出 Lifecycle、task 状态计数、Run/checkpoint/Store/filesystem 摘要 |
| `GET /api/workflow-lifecycles/{lifecycle_id}` | 获取一个 Lifecycle 摘要 |
| `DELETE /api/workflow-lifecycles/{lifecycle_id}` | 清理 parent/child Debug thread、Store prefix；active Run/task 时返回 409 |

删除时可选 `?delete_dynamic_directories=true` 清理本 Lifecycle 受管的动态目录。父 Run 到达 End 不会自动取消后台任务，
也不会自动删除 Lifecycle；必须先让后台 task 进入终态，再显式删除。Lifecycle 删除进入 `deleting` 后不再接受新的后台 Run，
清理失败时保留该状态以便继续清场。Lifecycle 摘要不返回 messages、Provider secret 或宿主路径。

下一步：[验证、启用和真实调用](06-validation-and-references.md)。
