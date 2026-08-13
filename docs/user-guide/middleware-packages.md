# 自定义 Middleware 包

自定义 Middleware 包让实例维护者把普通 LangChain `AgentMiddleware` 安装到 Agent 装配中。Agent Shell 不定义
第二套 Hook：模型、工具和 Agent 生命周期、state update、reducer、`Command`、短路及错误传播全部遵循
LangChain 官方语义。

## 包结构

每个包位于 `data/resources/custom_middlewares/<package-id>/`：

```text
request-context/
  middleware.json
  main.py
  requirements.txt  # 可选
```

`middleware.json` 使用固定格式：

```json
{
  "api_version": 1,
  "id": "request-context",
  "name": "Request context",
  "description": "Read the immutable request context from an official Middleware hook.",
  "config_schema": {
    "type": "object",
    "properties": {},
    "additionalProperties": false
  }
}
```

目录名必须与 `id` 相同。配置 Schema 只允许管理台能够机械渲染的扁平 object 子集。

`main.py` 只导出一个同步工厂：

```python
from langchain.agents.middleware import AgentMiddleware


class RequestContextMiddleware(AgentMiddleware):
    async def abefore_agent(self, state, runtime):
        request_messages = runtime.context.messages
        # Select and normalize messages for this Agent here, then return a
        # normal LangGraph state update when the Agent needs them.
        return None


def create_middleware(config, agent):
    return RequestContextMiddleware()
```

工厂可以返回一个 `AgentMiddleware`，也可以返回非空的 `list` 或 `tuple`。返回对象直接交给
`create_deep_agent(middleware=[...])`，Agent Shell 不代理官方 Hook。

## 装配与配置

Custom Middleware 组件保存有序包引用：

```json
{
  "name": "Request Middleware",
  "middlewares": [
    {
      "package_id": "request-context",
      "enabled": true,
      "config": {}
    }
  ]
}
```

Main Agent 选择该组件后使用这些包。直接 Subagent 按普通 capability 继承/替换/关闭规则决定自己的最终
Middleware 包列表。禁用项不导入、不执行；包不存在、格式无效、依赖未准备或配置不满足 Schema 时，保存或
请求装配会被拒绝。

## Runtime context 与 Graph State

`create_middleware` 的 `config` 和 `agent` 是构造期的普通配置值，不是 LangChain 的运行时对象。
执行时，Middleware 使用 LangChain 官方 hook 参数读取数据：

- `runtime.context.messages`：本次请求冻结的规范化 OpenAI `messages[]`；它不会自动进入提示词；
- `runtime.context.workflow`：当前 Workflow 的冻结元数据和 Graph 文档；
- `runtime.context.workflow_state`：wrapper 为当前画布 Agent invocation 提供的父 Workflow State 顶层只读快照；
- `runtime.context.workflow_node_id`、`agent_id`、`invocation_id`：当前画布节点、Agent Profile 和本次执行身份；
- `state` / `request.state`：当前 Agent graph 的可变 state，按官方 reducer 和 state update 语义读写。

用户消息应由 Middleware 按 Main Agent/Subagent 身份切分、整理，再从 `before_agent`/`abefore_agent` 返回
`{"messages": [...]}` 等官方 state update。不要把可恢复业务数据保存在 Middleware 实例属性或模块全局变量。

## Python 依赖与安全

可选 `requirements.txt` 每行声明一个普通 PyPI requirement。Windows 启动器根据全部有效包的依赖生成共享
`runtime/middleware_packages/site-packages/`；核心锁定依赖优先，包不能修改核心 runtime。

用户 Middleware 的依赖只属于实例扩展层。不得把这些依赖加入 Agent Shell 的 `pyproject.toml`、锁文件或
核心 `.venv`；否则用户包会污染项目运行环境，并把实例配置错误地变成项目源码依赖。删除旧插件 Hook 不影响
此边界：包加载和独立依赖准备继续保留，包的执行对象则统一使用官方 `AgentMiddleware`。

Middleware 包是受信任的任意 Python 代码，以 Agent Shell 服务进程权限运行，没有 sandbox。只允许实例维护者
写入该目录。
