# Workflow Prepare

Workflow Prepare 是 Workflow-owned 组件，Workflow 可绑定零或一个。它在所有 Agent 配置解析后、LangChain 对象构造前
执行一次：

```python
async def prepare(input):
    return {"context": {}}
```

`input` 是脱离配置仓库的 JSON-compatible 快照，包含请求事实、Workflow/Graph 和按 Workflow node ID 组织的 Agent
装配事实；不包含 graph、middleware、backend、state、句柄或 Provider secret value。当前只接受 `context` 返回字段，
并从本次调用的 `runtime.context.prepare` 读取。

`python_requirements` 每行一个 PEP 508 requirement。依赖修改后重启生效；源码修改在下一次 Workflow 调用生效。
