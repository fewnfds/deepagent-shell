# 准备

准备是 Workflow-owned 外围组件，Workflow 可绑定零或一个。它不是 LangChain middleware 或 LangGraph node。
管理台从 `data/templates/workflow/prepare/<template-key>/` 创建配置独占扩展，保存到
`data/config/python_package_instances/workflow-prepare/<configuration-uuid>/`。`main.py` 提供无参数同步工厂：

```python
def create_prepare():
    async def prepare(input):
        return {"context": {}}

    return prepare
```

Shell 在所有 Agent `StaticAssembly` 解析后、最终 Context 及 Router/Dispatcher/Agent/StateGraph 物化前执行一次
`prepare(input)`。
`input` 是脱离配置仓库的 JSON-compatible 快照，包含请求事实、Workflow/Graph 和按 Workflow node ID 组织的 Agent
装配事实；不包含 graph、middleware、backend、state、句柄或 Provider secret value。当前只接受 `context` 返回字段，
并从本次调用的 `runtime.context.prepare` 读取。

外部依赖逐行写入扩展目录的可选 `requirements.txt`。依赖修改后重启生效；Python 源码在下一次 Workflow 调用重新加载。
