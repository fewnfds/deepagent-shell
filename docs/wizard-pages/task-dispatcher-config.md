# 任务分发

任务分发是 Workflow 画布上的动态 map 节点。它从当前 Workflow State/Runtime Context 生成运行时数量的任务，Shell 使用
LangGraph 官方 `Send` 把任务发给一个或多个 Agent Node。画布只保存一个 Task Dispatcher Node 和候选 Dispatch Edge，
不会为每个城市或乡镇持久化临时 Node。

## 从内置示例创建

1. 打开【Workflow 组件 / 任务分发】，新建配置。
2. 选择 `内置示例-rainfall-task-dispatcher` 并保存。
3. 按实际 State 结构修改当前配置独占的 `main.py`。
4. 在 Workflow 画布加入 Task Dispatcher，选择该配置。
5. 建立 `dispatch_key=city` 到城市 Agent、`dispatch_key=town` 到乡镇 Agent 的 Dispatch Edge。

示例读取：

```python
state["shared_vars"] = {
    "cities": [{"id": "310100", "rainfall": [12.4, 8.1]}],
    "towns": [{"id": "310115-001", "rainfall": [7.2, 9.0]}],
}
```

并生成 `len(cities) + len(towns)` 个任务。源码位于
`examples/workflow-components/task-dispatcher/rainfall-task-dispatcher/`。

## Package 与入口

用户模板位于 `data/templates/workflow/task_dispatcher/<template-key>/`；首次保存后复制为
`data/config/python_package_instances/task-dispatcher/<configuration-uuid>/`。manifest 固定使用 `family: workflow-node`、
`adapter: task-dispatcher`。`main.py` 必须提供同步工厂：

```python
def create_dispatcher():
    async def dispatch(state, runtime):
        cities = state.get("shared_vars", {}).get("cities", [])
        return {
            "tasks": [
                {
                    "task_id": f"city:{city['id']}",
                    "dispatch_key": "city",
                    "payload": {"kind": "city", "record": city},
                }
                for city in cities
            ],
            "update": {"shared_vars": {"city_task_count": len(cities)}},
        }

    return dispatch
```

- `state` 是 detached 可变副本；`runtime` 是 LangGraph 注入的官方 `Runtime[WorkflowRuntimeContext]`。Lifecycle Store 使用
  `runtime.store`，后台 Run 命令使用 `runtime.context.background_runs`。不要把 Runtime 或 commands 写入 State/Store/checkpoint。
- `tasks` 必须有 1–1000 项；同一次调用中的 `task_id` 唯一，并应来自稳定业务身份。
- `dispatch_key` 必须与同源 Dispatch Edge 完全一致；同一个 key 只能连接一个目标。
- `payload` 必须是严格 JSON 对象，不能包含 Python 对象或 `NaN`、`Infinity` 等非有限数；worker 所需的本批数据都应放在这里。
- `update` 可以更新任意已声明 Workflow State channel，但每个值必须符合该 channel 的现有类型；它只更新父 State，
  不隐式改写本批显式 Send State。
- 包不 import LangGraph，不返回 Node ID、`Send` 或 `Command`。

没有任务时，第一阶段要求由上游 Condition Router 绕过 Dispatcher；返回空 `tasks` 会使运行失败。

## Worker 如何读取任务

Shell 为每项任务补充 `dispatcher_node_id` 与 `dispatcher_invocation_id`，形成 `WorkflowTaskContext`。目标 Agent 子图及其
Middleware 从私有 State 读取：

```python
task_from_state = state["workflow_task"]
```

worker 完成后，父 Workflow State 的 `agent_invocations` 轻量记录带不含 payload 的 `workflow_task` identity，因此下游启用
`defer=True` 的汇总 Agent 可以等待 pending worker 完成，再按 `(dispatcher_node_id, task_id)` 选择结果；完整 task payload
和 messages 通过 `result_ref` 从 Store 读取。

WIC 可以把 payload 编排进当前 worker 的私有 `messages`，但不负责任务认领或共享锁。任务并发由 LangGraph 调度，当前
Workflow 设置有限的 `max_concurrency`，任一 worker 未处理的异常会使本次运行 fail-fast。

这些 Python 代码运行在服务进程的受信任边界内，没有 sandbox。源码在下一次 Workflow 请求重新加载；
`requirements.txt` 修改后需要重启 Agent Shell。
