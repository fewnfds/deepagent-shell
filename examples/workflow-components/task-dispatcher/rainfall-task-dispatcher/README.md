# Rainfall Task Dispatcher

这个内置示例从 `state["shared_vars"]` 读取城市和乡镇列表，为每条记录创建一个独立 Workflow task。

```python
{
    "cities": [{"id": "city-1", "rainfall": [12.0, 18.5]}],
    "towns": [{"id": "town-1", "rainfall": [8.0]}],
}
```

## 使用

1. 在 Workflow 组件的 Task Dispatcher 页面从 `内置示例-rainfall-task-dispatcher` 新建配置；
2. 在画布加入 Task Dispatcher Node 并选择该配置；
3. 建立 `dispatch_key=city` 的 Dispatch Edge 到城市 worker Node；
4. 建立 `dispatch_key=town` 的 Dispatch Edge 到乡镇 worker Node；
5. 上游 Node 在 `shared_vars.cities` 和 `shared_vars.towns` 写入待处理记录。

每个下游 worker 在自己的私有 State 中收到一份 `workflow_task`：

```python
{
    "dispatcher_node_id": "rainfall-dispatcher",
    "dispatcher_invocation_id": "<runtime task id>",
    "task_id": "city:city-1",
    "dispatch_key": "city",
    "payload": {
        "kind": "city",
        "record": {"id": "city-1", "rainfall": [12.0, 18.5]},
    },
}
```

用户可以修改 `main.py` 改变数据来源、任务粒度、key 和 payload，但固定入口仍是 `create_dispatcher()`，返回的
异步函数仍接收 `state, runtime` 并返回 `tasks + update`。不要在 package 中返回 Node ID、`Send` 或 `Command`。
