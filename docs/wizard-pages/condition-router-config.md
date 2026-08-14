# 条件路由

条件路由是 Workflow 画布上的可编程 `Command` 节点。组件配置只保存 Python 脚本和可选
`python_requirements`；分支不在组件页重复配置，而由画布上从该节点发出的具名 Branch Edge 定义。

脚本入口固定为：

```python
async def route(state, context):
    return {
        "activate": ["manual_review", "audit"],
        "update": {"shared_vars": {"routed": True}},
    }
```

- `state` 是完整 Workflow State，包含当前存在的 `shared_vars`、`agent_invocations` 和 `files`；允许直接修改，也可通过 `update` 返回局部更新。
- `context` 是完整 Workflow Runtime Context，包含请求消息快照、Workflow、Prepare 结果和当前已有的运行字段。
- `activate` 必须是 Branch Edge key 列表，可以同时激活多个不同分支；key 必须与画布 Edge 上填写的值完全一致。
- `update` 必须是 Workflow State 的局部映射，只能更新当前 State contract 已声明的顶层字段。
- 空的 `activate` 自动使用 `otherwise`；`otherwise` 必须在画布上显式连接，且不能和其他分支同时返回。
- 返回未知或未连接的 key、重复 key、非法 State 字段或异常都会使本次 Workflow 运行失败。

运行时把结果映射为 LangGraph `Command(update=..., goto=[...])`。Branch Edge 只负责声明候选目标，不会再注册为静态
`add_edge`，因此未被 `activate` 选中的分支不会执行。

这些 Python 代码运行在服务进程的受信任边界内，没有 sandbox。`python_requirements` 每行一个 PEP 508 requirement；
依赖修改后重启生效，源码修改在下一次 Workflow 调用生效。
