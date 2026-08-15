# 条件路由

条件路由是 Workflow 画布上的可编程控制节点。组件配置保存一个独占的 Python 扩展目录引用和该扩展声明的普通
`config`；分支不在组件页重复配置，而由画布上从该节点发出的具名 Branch Edge 定义。

## Package 与入口

静态模板位于 `data/templates/workflow/condition_router/<template-key>/`。新配置首次保存时复制为
`data/config/python_package_instances/condition-router/<configuration-uuid>--<template-slug>--<instance-uuid>/` 下的配置扩展。
配置扩展至少包含 `package.json` 和 `main.py`，并可包含 `requirements.txt`、本地模块和测试。Router manifest 固定使用 `family: workflow-node` 与
`adapter: condition-router`。完整目录、manifest、imports 和依赖规则见[文件化 Python 扩展包](../user-guide/middleware-packages.md)。

`main.py` 必须提供同步工厂 `create_router(config)`，工厂返回固定签名的 async callable：

```python
def create_router(config):
    threshold = config["threshold"]

    async def route(state, context):
        risk = state.get("shared_vars", {}).get("risk", 0)
        branch = "manual_review" if risk >= threshold else "otherwise"
        return {
            "activate": [branch],
            "update": {"shared_vars": {"routed": True}},
        }

    return route
```

`package.json.config_schema` 声明的扁平字符串、整数、数字、布尔和枚举字段会机械生成组件配置控件。新建页自动加载模板并
提供完整 `main.py`、`requirements.txt` 和普通 config；已有配置只读取自己的扩展代码目录。Schema 输入只更新组件 YAML，
代码输入更新对应扩展文件。额外文件由用户直接在扩展代码目录维护，前端不解析或改写。

每个 Condition Router 配置都拥有独立的 Python 扩展。复制配置会复制新的扩展目录；模板或其他配置的扩展发生变化都不会影响它。

## Route 返回值

- `state` 是完整 Workflow State 的独立可变副本，包含当前存在的 `shared_vars`、`agent_invocations` 和 `files`；可以修改副本，
  也可以通过 `update` 返回局部更新。
- `context` 是完整 Workflow Runtime Context 的独立映射，包含请求消息快照、Workflow、Prepare 结果和当前已有的运行字段。
- `activate` 必须是 Branch Edge key 列表，可以同时激活多个不同分支；key 必须与画布 Edge 上填写的值完全一致。
- `update` 必须是 Workflow State 的局部映射，只能更新当前 State contract 已声明的顶层字段。
- 空的 `activate` 自动使用 `otherwise`；`otherwise` 必须在画布上显式连接，且不能和其他分支同时返回。
- 返回未知或未连接的 key、重复 key、非法 State 字段、无效入口或异常都会使本次 Workflow 运行失败。

运行时把结果映射为 LangGraph `Command(update=..., goto=[...])`。Branch Edge 只负责声明候选目标，不会再注册为静态
`add_edge`，因此未被 `activate` 选中的分支不会执行。package 不接触画布 Node ID，也不直接返回 `Command`。

这些 Python 代码运行在服务进程的受信任边界内，没有 sandbox。源码修改在下一次 Workflow 请求重新加载；
`requirements.txt` 修改后必须重启 Agent Shell，依赖状态才会重新准备。
