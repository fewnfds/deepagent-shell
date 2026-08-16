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
    async def dispatch(state, context):
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

- `state` 和 `context` 是 detached 副本/映射；包不能持有运行时内部对象。
- `tasks` 必须有 1–1000 项；同一次调用中的 `task_id` 唯一，并应来自稳定业务身份。
- `dispatch_key` 必须与同源 Dispatch Edge 完全一致；同一个 key 只能连接一个目标。
- `payload` 必须是 JSON 对象；worker 所需的本批数据都应放在这里。
- `update` 只更新父 Workflow State 的已声明 channel，不隐式改写本批显式 Send State。
- 包不 import LangGraph，不返回 Node ID、`Send` 或 `Command`。

没有任务时，第一阶段要求由上游 Condition Router 绕过 Dispatcher；返回空 `tasks` 会使运行失败。

## Worker 如何读取任务

Shell 为每项任务补充 `dispatcher_node_id` 与 `dispatcher_invocation_id`，形成 `WorkflowTaskContext`。目标 Agent 子图及其
Middleware 可从两处读取同一内容：

```python
task_from_state = state["workflow_task"]
task_from_context = runtime.context.workflow_task
```

worker 完成后，父 Workflow State 的 `agent_invocations` 记录也带 `workflow_task`，因此下游启用 `defer=True` 的汇总
Agent 可以等待 pending worker 完成，再按 `(dispatcher_node_id, dispatcher_invocation_id, task_id)` 选择结果。

WIC 可以把 payload 编排进当前 worker 的私有 `messages`，但不负责任务认领或共享锁。任务并发由 LangGraph 调度，当前
Workflow 设置有限的 `max_concurrency`，任一 worker 未处理的异常会使本次运行 fail-fast。

这些 Python 代码运行在服务进程的受信任边界内，没有 sandbox。源码在下一次 Workflow 请求重新加载；
`requirements.txt` 修改后需要重启 Agent Shell。
