# Item-list Task Dispatcher

这是 Task Dispatcher 的可修改示例。示例把 `state["shared_vars"]["items"]` 中的每个对象转换成一个独立 task：

```python
{"items": [{"id": "item-1", "value": 42}]}
```

`items`、`item`、task ID 和 payload 都只是示例策略。Dispatcher 可以按业务需要读取完整 Workflow State、
`runtime.context` 或 `runtime.store`；画布只需为脚本实际返回的每个 `dispatch_key` 提供对应 Dispatch Edge。目标 Agent
如何消费私有 `workflow_task`，由它自己的 WIC 决定。

## 稳定 contract

- `create_dispatcher()` 是无参数同步工厂；
- 工厂返回固定签名的 `async dispatch(state, runtime)`；
- `dispatch` 可以从完整 Workflow State、官方 Runtime Context 或 Store 选择任务来源；
- 每批必须生成 1-1000 个 task；
- `task_id` 在本批唯一，并来自稳定业务 ID；
- `dispatch_key` 只引用画布 Dispatch Edge key，不引用 Node ID；
- `payload` 是严格 JSON object；
- `update` 可以更新当前 Workflow State 已声明的任意顶层 channel，也可以返回空对象；
- package 不 import 或返回 LangGraph `Send` 或 `Command`。

当前 contract 不接受空任务集合；建议在可能为空时由上游 Command Node 绕过 Dispatcher。如何读取任务、划分粒度、
生成 ID、选择目标和更新父 State，都由当前 Workflow 决定。

模板只使用 Python 标准库，`requirements.txt` 不声明第三方依赖。
