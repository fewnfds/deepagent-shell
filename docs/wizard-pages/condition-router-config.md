# 条件路由

条件路由是 Workflow 画布上的可编程控制节点。组件配置保存一个独占的 Python 扩展目录引用和管理台显示的有序文件路径；
分支不在组件页重复配置，而由画布上从该节点发出的具名 Branch Edge 定义。

## Package 与入口

静态模板位于 `data/templates/workflow/condition_router/<template-key>/`。新配置首次保存时复制为
`data/config/python_package_instances/condition-router/<configuration-uuid>/` 下的配置扩展。
配置扩展至少包含 `package.json` 和 `main.py`，并可包含 `requirements.txt`、本地模块和测试。Router manifest 固定使用 `family: workflow-node` 与
`adapter: condition-router`。完整目录、manifest、imports 和依赖规则见[文件化 Python 扩展包](../user-guide/middleware-packages.md)。

`main.py` 必须提供同步工厂 `create_router()`，工厂返回固定签名的 async callable：

```python
def create_router():
    threshold = 80

    async def route(state, runtime):
        risk = state.get("shared_vars", {}).get("risk", 0)
        branch = "manual_review" if risk >= threshold else "otherwise"
        return {
            "activate": [branch],
            "update": {"shared_vars": {"routed": True}},
        }

    return route
```

新建页可以选择现有模板，也可以【套用空模板】从空的 `main.py` 开始。用户可以逐行增加包内相对文件路径；编辑器按清单顺序显示并保存这些文本文件。
不存在的文件只显示警告，填写内容并保存后创建。已有配置只读取自己的扩展代码目录，未列出的额外文件保持原样。

每个 Condition Router 配置都拥有独立的 Python 扩展。复制配置会复制新的扩展目录；模板或其他配置的扩展发生变化都不会影响它。

## Route 返回值

- `state` 是完整 Workflow State 的独立可变副本，包含当前存在的 `shared_vars`、`agent_invocations` 和 `files`；可以修改副本，
  也可以通过 `update` 返回局部更新。
- `runtime` 是 LangGraph 注入的官方 `Runtime[WorkflowRuntimeContext]`。本次 Run 的静态身份与配置在 `runtime.context`；Lifecycle
  Store 在 `runtime.store`；后台 Run 命令在 `runtime.context.background_runs`。它不是 detached dict，也不要使用全局 service locator。
- `activate` 必须是 Branch Edge key 列表，可以同时激活多个不同分支；key 必须与画布中选中 Edge 后在属性栏填写的值完全一致，
  不会显示在线段上。
- `update` 必须是 Workflow State 的局部映射，只能更新当前 State contract 已声明的顶层字段。
- 空的 `activate` 自动使用 `otherwise`；`otherwise` 必须在画布上显式连接并在 Edge 属性中填写，且不能和其他分支同时返回。
- 返回未知或未连接的 key、重复 key、非法 State 字段、无效入口或异常都会使本次 Workflow 运行失败。

运行时把结果映射为 LangGraph `Command(update=..., goto=[...])`。Branch Edge 只负责声明候选目标，不会再注册为静态
`add_edge`，因此未被 `activate` 选中的分支不会执行。package 不接触画布 Node ID，也不直接返回 `Command`。

这些 Python 代码运行在服务进程的受信任边界内，没有 sandbox。源码修改在下一次 Workflow 请求重新加载；
`requirements.txt` 修改后必须重启 Agent Shell，依赖状态才会重新准备。
