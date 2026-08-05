# 使用自动化插件

【自动化】是按 Agent 身份挂载的 Python 插件系统。每个 Primary 配置或 Subagent 配置都可以拥有一组有序
插件 binding；binding 保存插件 ID、启用状态和一份 JSON config。

插件有两类执行边界：

- Agent 内部使用 LangChain 原生 `AgentMiddleware`，可以实现完整 model/tool Hook；
- Agent Shell 额外提供 `prepare`、请求生命期 `lifecycle` 和终态 `complete`。

Shell 不复制 LangChain 的 Hook 调度器。插件返回 Middleware 后，Shell 把它放入
`deepagents.create_deep_agent(middleware=[...])`；LangChain 运行到相应节点时直接调用插件的方法。

## 插件包

在【系统 / 文件管理 / 自动化脚本】下创建一目录一个插件包。目录名必须与 manifest ID 相同：

```text
automation_scripts/market-context/
  script.json
  main.py
  requirements.txt  # 可选
```

当前唯一 manifest 版本是 v2：

```json
{
  "api_version": 2,
  "id": "market-context",
  "name": "Market context",
  "description": "Prepare current market context for this Agent.",
  "entrypoints": ["middleware", "prepare", "lifecycle", "complete"]
}
```

`entrypoints` 至少声明一项主要入口（`middleware`、`prepare` 或 `lifecycle`），并可附带 `complete`；只能包含：

| 声明 | `main.py` 入口 | 所属边界 |
| --- | --- | --- |
| `middleware` | `def create_middleware(ctx)` | LangChain Agent Hook |
| `prepare` | `async def prepare(ctx)` | 所有 Agent 图构造前 |
| `lifecycle` | `async def lifecycle(ctx)` | 请求生命期 fixed-delay 循环 |
| `complete` | `async def complete(ctx)` | 请求所有终态之后 |

未声明的入口不会执行。扫描目录时只做 manifest、UTF-8、Python AST 和函数签名检查，不 import `main.py`。
插件实际被启用的 Agent 使用时才会 request-local import，并在请求清理时移除模块。插件可包含辅助文件和资产；
相对 import 正常可用：

```python
from .market_client import load_current_market
```

## LangChain Hook

`create_middleware(ctx)` 返回一个 `AgentMiddleware`，也可以返回有序的 Middleware `list` 或 `tuple`：

```python
from langchain.agents.middleware import AgentMiddleware


class MarketMiddleware(AgentMiddleware):
    def __init__(self, ctx):
        self.ctx = ctx

    async def abefore_model(self, state, runtime):
        market = self.ctx.vars.get((self.ctx.agent["id"], "market"))
        self.ctx.log(f"market context ready: {market is not None}")
        return None

    async def awrap_tool_call(self, request, handler):
        result = await handler(request)
        return result


def create_middleware(ctx):
    return MarketMiddleware(ctx)
```

插件类可以使用 LangChain 当前提供的完整同步或异步方法：

- `before_agent` / `abefore_agent`
- `before_model` / `abefore_model`
- `wrap_model_call` / `awrap_model_call`
- `after_model` / `aafter_model`
- `wrap_tool_call` / `awrap_tool_call`
- `after_agent` / `aafter_agent`

Hook 方法的 `state`、`runtime`、`request`、`handler`、response 和返回值都是 LangChain 原生对象。短路、重试、
handler 调用次数、state update、`Command` 和错误传播都按 LangChain 规则执行。插件 Middleware 的
`state_schema`、`tools` 和 `transformers` 也直接交给 Agent factory，不经过 JSON 转换或 Shell adapter。

binding 顺序就是最终 Middleware 顺序。before、after 和 wrap 的正序、逆序与嵌套由 LangChain 根据该列表
处理。插件不要假设并行工具或递归 Subagent 是串行的；需要图内并发一致性的值应放入 LangGraph state，
请求级便利数据可放入下述 `ctx.vars`。

## Shell 生命周期

### prepare

`prepare` 在配置快照解析完成后、任何 Primary/Subagent `create_deep_agent()` 之前按 Agent 和 Hook binding 顺序执行：

```python
async def prepare(ctx):
    current = await load_current_market()
    ctx.vars[(ctx.agent["id"], "market")] = current
    ctx.messages.extend([
        {"role": "user", "content": "Current market data follows."},
        {"role": "assistant", "content": str(current)},
    ])
```

每个 Agent 身份的 `ctx.messages` 初始为空。此阶段可以显式追加当前身份需要的活动消息、写入
`ctx.initial_files`，或准备 Skill overlay；原始客户端消息不会自动复制进来。所有 Agent 身份的 prepare 结束后，
Shell 统一校验派生消息；空列表合法，无效 role/content 会在构造 Agent 图前失败。

Subagent 每次调用仍使用新的 LangGraph state。prepare 产出基础消息时，输入顺序是这些基础消息再加本次
`task` delegated messages；没有产出时保持 Deep Agents 原生 delegated input，不执行 Shell 消息重建。静态
system prompt 单独由 `create_deep_agent(system_prompt=...)` 装配。

### lifecycle

每个启用的周期 binding 都保存自己的 `interval_seconds`，并在一次 API 请求内拥有一个独立 fixed-delay
循环。首轮在所有 Agent 构造成功后立即开始；本轮 `lifecycle(ctx)` 返回后再等待该 binding 的间隔，不重叠、
不补跑。不同周期 binding 可以使用不同间隔并彼此独立运行。

一次 lifecycle 调用失败只停止这个周期 binding 的循环，不影响同一 Agent 的其他周期插件，不接管 Agent
graph，也不自动 retry。lifecycle 不热修改
已经启动的模型上下文；可以更新 `ctx.vars`、外部服务或 mapped 文件，供后续 Hook/工具读取。

### complete

请求正常完成、失败、超时、取消或客户端断开后，Shell 先停止产生新的 lifecycle tick，等待正在运行的一轮
自然返回，再分别按 Hook 和周期 binding 顺序调用声明的 `complete`：

```python
async def complete(ctx):
    ctx.log(ctx.terminal["status"])
```

`complete` 是 Shell graph 外的终态边界，不等同于 LangChain `after_agent`。complete 失败只记录安全日志，
不会替换已经确定的公开响应。

## Agent 配置

Primary 的 `automation` 直接保存：

```json
{
  "hooks": [
    {
      "plugin_id": "market-context",
      "enabled": true,
      "config": {"market": "example"}
    }
  ],
  "periodic": [
    {
      "plugin_id": "market-refresh",
      "enabled": true,
      "config": {"market": "example"},
      "interval_seconds": 5
    }
  ]
}
```

Hook binding 只执行 `prepare`、`middleware` 和 `complete`；周期 binding 只执行 `lifecycle` 和 `complete`。
同一个插件可以分别挂在两类列表，也可以用不同 config 挂载多次；每个 binding 有独立模块实例，但共享本请求的
`ctx.vars`。`enabled=false` 的 binding 不 import、不执行，也不因第三方依赖未准备而阻止请求。

Subagent 对 `hooks` 和 `periodic` 分别使用一种模式：

- `inherit`：使用当前 Primary 的同类 bindings；
- `replace`：使用这个 Subagent 自己保存的同类 bindings；
- `disabled`：不使用这类插件。

因此可以继承 Hook 插件同时关闭周期插件，反之亦然。同一个 Subagent profile 无论从 diamond 还是显式递归
到达，在一次请求中只有一个 Agent 身份上下文；每个周期 binding 最多有一个循环。每次 `task` invocation 的
LangGraph state 仍然独立。

## ctx 与不可变原始消息

`ctx.request.messages` 是本次 OpenAI 请求通过权威校验并规范化后的 `messages[]`。OpenAI parts 已转为 LangChain
标准 blocks；API history 另行保留原始 wire。该对象是只读 tuple，每条消息、content 列表和嵌套 block 都递归只读：

- 同一请求的 prepare、Middleware、lifecycle、complete 和全部 Agent 身份看到相同内容；
- prepare 对 `ctx.messages` 的修改不会改变它；
- LangChain state 更新不会改变它；
- 下一次 API 请求根据客户端新提交的完整 messages 重新建立。

插件要稳定切分 Primary 用户信息时，应始终从 `ctx.request.messages` 开始计算，并为当前 Agent 建立可写深复制后
写入 `ctx.messages`；也可以直接把只读消息加入 `ctx.messages`，Shell 会在 prepare 终点规范化为该 owner 独立的
可写副本。不要原地修改只读 block，也不要把前序插件已经修改的工作列表当作原始事实。多模态正文应留在消息
content blocks 中，不要经 `ctx.vars` 进行无意义中转。

所有插件边界可用：

- `ctx.request.id`、`ctx.request.messages`
- `ctx.agent`：只读 `id/type/name`
- `ctx.plugin`：只读 `id/kind/binding_index`，`kind` 为 `hook` 或 `periodic`
- `ctx.config`：当前 binding 的只读 JSON 配置
- `ctx.vars`：本次请求全部 binding 共享的普通 Python dict
- `ctx.paths.plugin_dir`、`runtime_dir`、`mapped`
- `ctx.stage`、`ctx.tick`、`ctx.terminal`
- `ctx.log(value)`

只有 prepare 额外提供可写 `ctx.messages`、`ctx.initial_files` 和：

```python
overlay = ctx.prepare_skill("my-skill", mode="overlay")
persistent = ctx.prepare_skill("my-skill", mode="persistent")
```

`ctx.vars` 不自动建立 request/agent/plugin namespace，也不复制或序列化值，不设单值 256 KiB 限制。全部 binding
拿到同一个 dict 对象，可用任意 hashable key 保存 Python 对象引用。需要隔离时使用 `ctx.agent["id"]`、
`ctx.plugin["id"]`、`kind` 和 `binding_index` 自行构造 tuple 或字符串 key；展示名称不适合作唯一键。平台不为该
dict 提供锁、CAS 或事务，并行 Hook 对共享可变对象的协调由插件负责。dict 只存活于一次 API 请求；跨请求持久化
仍由插件自行使用数据库、文件或外部服务。

## Invocation 身份与 scratch

Primary 每次请求有一个 root invocation；每次实际 `task` 委派，包括同 profile 的并行、嵌套和递归调用，都会建立
新的 Shell UUID。插件 Middleware 在 Agent Hook 的 LangGraph runtime 中读取只读身份：

```python
class WorkspaceMiddleware(AgentMiddleware):
    def __init__(self, ctx):
        self.ctx = ctx

    async def abefore_agent(self, state, runtime):
        invocation = runtime.context["agent_shell_invocation"]
        binding_key = (
            f"{self.ctx.plugin['kind']}:"
            f"{self.ctx.plugin['binding_index']}"
        )
        scratch = invocation["workspaces"][binding_key]
        (scratch / "result.tmp").write_bytes(b"working data")
```

`agent_shell_invocation` 提供：

- `request_id`、`id`、`parent_id`、`cause_tool_call_id`；
- `agent_id`、`agent_type`、`agent_name`；
- `workspaces`：当前 Agent 各启用 Hook binding 的只读 scratch `Path` mapping，key 为 `hook:<binding_index>`。

同一 invocation 内的多次 model/tool call 使用同一个 ID 和 scratch；四次并发启动同一个 Subagent 会得到四个目录。
平台目录形状为：

```text
runtime/automation/<request-id>/owners/<agent-id>/
  bindings/<kind>-<binding-index>/
    invocations/<invocation-id>/scratch/
```

`ctx.paths.runtime_dir` 是当前 binding 的 request-local 根目录，适用于 prepare/lifecycle/complete 等没有“当前
invocation”的边界；不要把它误当作并行 Subagent scratch。Middleware factory 和共享 `ctx` 也没有可变的
`ctx.invocation_id`，因为同一实例会被并发 invocation 复用。需要 invocation 私有变量时使用 LangGraph state，或把
`invocation["id"]` 编入共享 `ctx.vars` key。

请求终态会在所有 `complete` 返回后删除整棵 `runtime/automation/<request-id>/`。这只是默认目录隔离，不是
filesystem sandbox，也不改变 Deep Agents 的请求级共享 workspace。插件主动写 mapped path、数据库、对象存储或
其他宿主文件时，仍需自行建立副本、唯一命名、锁、事务或原子替换。

## Python 依赖（Windows）

可选 `requirements.txt` 每行声明一个普通 PyPI requirement：

```text
Pillow>=11,<13
openpyxl==3.1.5
```

Windows 启动器把全部有效自动化插件的兼容依赖并集原子生成到
`runtime/automation_plugins/site-packages/`。核心 site-packages 始终优先，并以当前 runtime 的完整版本作为
约束；插件不能升级、降级或替换 Agent Shell、LangChain、LangGraph 或 Deep Agents 依赖。

requirements 变化后停止并重新启动 Agent Shell。安装只发生在受控启动阶段，请求处理期间不会调用 pip/uv。
当前只接受公开 PyPI 的普通 PEP 508 requirement、当前 Windows/Python 可用的二进制 wheel；不接受 URL、VCS、
本地路径、editable、额外索引或源码构建。该层是实例共享环境，不是每插件独立 venv，互斥依赖无法同时使用。

Docker 当前不准备动态插件依赖；带非空 requirements 的插件会保持依赖未就绪。

## 权限、失败与一致性

自动化插件是实例维护者信任并安装的任意 Python 代码，以 Agent Shell 服务进程完整权限运行，没有 sandbox。
它可以访问网络、文件、进程、数据库和第三方服务。平台不限制业务副作用，也不提供事务、回滚、冲突协调或
强制超时。

prepare 或 Middleware 构造失败会阻止请求；LangChain Hook 的错误按 Agent graph 原生规则传播；lifecycle 错误
只停止对应循环；complete 错误只记录日志。平台不提供 `request_graph_stop()`，插件不能通过 Shell 私有信号接管
graph 终止条件。

插件必须有限返回，并自行保证外部操作一致性：数据库批量更新使用事务，文件先完整写临时文件再原子替换，
网络协议按服务端幂等规则设计。插件自己创建的线程、子进程或后台 Task 不归平台发现、等待或终止。
