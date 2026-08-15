# 文件化 Python 扩展包

Agent Shell 把用户代码保存为真实 Python package，组件 YAML 只保存稳定 UUID 和普通配置。目前支持两个窄 adapter：

- `middleware/agent-middleware`：物化 LangChain 官方 `AgentMiddleware`；
- `workflow-node/condition-router`：为画布 Condition Router 物化 async route callable。

两者共享文件格式、依赖准备和模块加载，但运行 contract 互不通用。系统不提供万能 Python Node。

## 目录与 Manifest

每个包位于 `data/resources/python_packages/<package-uuid>/`：

```text
11111111-1111-4111-8111-111111111111/
  package.json
  main.py
  requirements.txt  # 可选
  helpers.py         # 可选
  tests/             # 可选
```

目录名必须与 `package.json.id` 完全相同，ID 必须是小写规范 UUID。`package.json` 的固定外壳如下：

```json
{
  "format_version": 1,
  "id": "11111111-1111-4111-8111-111111111111",
  "family": "workflow-node",
  "adapter": "condition-router",
  "name": "Risk router",
  "description": "Route high-risk work for review.",
  "config_schema": {
    "type": "object",
    "properties": {
      "threshold": {
        "type": "integer",
        "title": "Threshold",
        "default": 80,
        "minimum": 0,
        "maximum": 100
      }
    },
    "required": ["threshold"],
    "additionalProperties": false
  }
}
```

`config_schema` 只支持管理台能机械渲染的扁平字符串、整数、数字、布尔和枚举。Python 对象、callable 和嵌套运行参数由
`main.py` 根据普通配置构造，不写入 YAML。

## Condition Router 模板

Router manifest 使用 `family: workflow-node` 和 `adapter: condition-router`。`main.py` 必须提供同步工厂，工厂返回 async callable：

```python
def create_router(config):
    threshold = config["threshold"]

    async def route(state, context):
        risk = state.get("shared_vars", {}).get("risk", 0)
        branch = "review" if risk >= threshold else "otherwise"
        return {"activate": [branch], "update": {}}

    return route
```

`route(state, context)` 必须正好接收这两个参数，并返回 `{activate, update}`。`activate` 只能包含当前 Router 画布 Branch Edge
已有的 branch key；空列表使用 `otherwise`。`update` 只能更新 Agent Shell Workflow State 的现有 channel。目标 Node ID 与
branch key 到 Node 的映射始终由 compiler/画布拥有，package 不能返回目标 Node ID 或 `Command`。

Router 可能因 Graph 重试或恢复被重复调用，业务代码应保持幂等，不在模块全局变量中保存可恢复状态。

## AgentMiddleware 模板

Middleware manifest 使用 `family: middleware` 和 `adapter: agent-middleware`。工厂返回一个官方 `AgentMiddleware`，或返回非空
`list`/`tuple`：

```python
from langchain.agents.middleware import ModelCallLimitMiddleware


def create_middleware(config, agent):
    return ModelCallLimitMiddleware(run_limit=config["limit"])
```

也可以从 `requirements.txt` 安装的库导入用户 Middleware。返回对象直接进入 Main Agent 或 Subagent 的
`create_deep_agent(middleware=[...])`；Agent Shell 不代理官方 hook、state schema、tools 或 stream transformer。

Agent Shell 使用 `astream` 异步 Agent 执行链。自定义 Middleware 实现 hook 时必须提供对应 async 版本，例如
`abefore_agent`、`abefore_model`、`aafter_model`、`aafter_agent`、`awrap_model_call` 或 `awrap_tool_call`；只覆盖同步 hook
而没有对应 async hook 的 package 会在物化时被拒绝。官方预置 Middleware 若同时提供同步和异步实现可以直接使用。

## 配置绑定

Condition Router 与 Custom Middleware 组件统一保存：

```yaml
python_package_bindings:
  - package_id: 11111111-1111-4111-8111-111111111111
    enabled: true
    config:
      threshold: 80
```

Condition Router 要求恰好一个 enabled binding；Custom Middleware 支持有序多个 binding。YAML 不保存源码、requirements、
绝对路径、入口符号或环境 fingerprint。修改 package display name 不影响引用。

## Imports、依赖与生效

Python 仍要求显式 `import`。包可以使用 Agent Shell 核心环境已经安装的库，但源文件没有导入名称时不能直接使用它。非核心直接
依赖必须逐行写入可选 `requirements.txt`。本地模块使用正常 package 相对导入，例如 `from .helpers import build_route`。

Windows 启动器只为当前配置中已启用 binding 引用的包收集 requirements，并生成可重建的
`runtime/python_packages/site-packages/`。核心锁定依赖优先；只接受普通 PyPI requirement、与核心约束兼容且提供 Windows wheel
的版本，不接受 URL、本地路径、`.pth` 或只有源码发行包的依赖。

Python 源码修改在下一次请求重新加载；requirements 修改需要重启 Agent Shell。package 作者可以直接用 IDE、pytest、类型检查和
版本控制维护完整目录。真实异常链和路径只应在 management-only Debug 中查看。

## 安全

Python package 是受信任的任意代码，以 Agent Shell 服务进程权限运行，不是 sandbox。只允许实例维护者写入
`data/resources/python_packages/`，不要在 package 或 manifest 中保存 secret。
