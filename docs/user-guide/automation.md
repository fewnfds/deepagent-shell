# 使用自动化插件

【自动化】是按 Agent 身份挂载的 Python 插件系统。每个 Main Agent 配置或 Subagent 配置都可以拥有一组有序
插件 binding；binding 保存插件 ID、启用状态和一份由插件 Schema 定义的 config。管理台根据 Schema 显示固定
字段表单，用户不再手写整段 config JSON；草稿校验和保存仍由后端执行权威 Schema 校验。

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

当前唯一 manifest 版本是 v3：

```json
{
  "api_version": 3,
  "id": "market-context",
  "name": "Market context",
  "description": "Prepare current market context for this Agent.",
  "entrypoints": ["middleware", "prepare", "lifecycle", "complete"],
  "config_schema": {
    "type": "object",
    "properties": {
      "market": {
        "type": "string",
        "title": "Market",
        "description": "Market identifier used by this binding.",
        "default": "example"
      }
    },
    "required": ["market"],
    "additionalProperties": false
  }
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

### 配置 Schema

`config_schema` 必须是 `type: object` 且 `additionalProperties: false`。当前只接受管理台可稳定渲染的扁平
子集：`string/integer/number/boolean`、`enum/default/required`、字符串长度与 pattern、数字上下界，以及字符串
`format: python` 和 `contentMediaType`。不接受 `$ref`、组合 Schema、数组、嵌套对象或递归结构。

字符串字段在管理台初始显示为一行 textarea，可向下拉大；Python 字段使用等宽字体；枚举、布尔和数字分别
显示为 select、switch 和 number input。切换插件时，旧插件 config 会被丢弃，并根据新 Schema 中明确声明的
`default` 重建。前端只产生结构化 payload，不复制后端校验规则。

`format: python` 会在保存前做语法检查，但该字段不是低权限表达式：插件若编译执行它，代码仍以 Agent Shell
服务进程完整权限运行。不要把不受信任的终端用户输入放进这类配置。

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

`prepare` 在配置快照解析完成后、任何 Main Agent/Subagent `create_deep_agent()` 之前按 Agent 和 Hook binding 顺序执行：

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

### 消息注入示例

源码仓库 `examples/automation-plugins/` 提供三个可直接复制到实例自动化脚本目录的示例：

- `main-agent-message-injection`：使用 `prepare`，每个 Main Agent API 请求转换并注入一次；
- `subagent-message-injection`：使用原生 `AgentMiddleware.abefore_agent`，每次真实 Subagent invocation 都编辑
  当前 `state["messages"]` 的深复制。它不使用 `wrap_model_call`，工具/模型循环不会重复注入；
- `subagent-filesystem-prompt-injection`：读取当前 Subagent filesystem 中的分组文件，将生成的消息插到 delegated
  task 前。配置是普通多行文本字段，管理端直接显示为文本框。

两者的 Schema 表单预置以下异步函数骨架：

```python
async def transform_messages(messages, ctx, state, runtime):
    # Edit the fresh mutable messages here.
    return messages
```

默认函数是身份变换，完整 `messages[]` 直接进入目标 Agent。Main Agent 返回 `[]` 表示本次不注入；Subagent 返回
`[]` 表示有意清空本次 invocation 输入。Main Agent 的 `state/runtime` 为 `None`；Subagent 得到当前 LangGraph 原生
对象，同一 profile 被调用四次会执行四次函数，并得到四个 invocation ID。

Subagent 变换函数拿到的最后一条消息通常是 Main Agent delegated task。标准的 Task 前插入写法是：

```python
async def transform_messages(messages, ctx, state, runtime):
    messages.insert(-1, {"role": "user", "content": "当前插件的提示词"})
    return messages
```

插件按页面绑定顺序依次读取前一插件已经更新的当前 state。因此 A、B、C 都用上述写法时，顺序是
`[A, B, C, delegated task]`，task 只有一条。实现通过 `REMOVE_ALL_MESSAGES` 重建本次内存列表顺序，因为默认
`add_messages` reducer 只支持末尾追加和按消息 ID 原位替换，不提供任意下标插入；它不删除持久化历史。

Main Agent 变换函数返回后，开头连续的 system 消息保持 system；首个非 system 之后的 system 原位改为 user。
Subagent 变换直接返回当前 LangGraph 消息对象或可转换的消息 dict，不额外改写 role、楼层或 content。无插件时
core 仍不会把客户端消息交给 Main Agent 或 Subagent。

Filesystem 提示词插件使用以下严格文本格式：

```ini
[group: cot]
[assistant]
# cot
[/draft/cot.md][1000]

[group: parts]
[assistant]
# part 1
[/draft/draft-1.md][1000]
[/output/output-1.md][1000]

[assistant]
# part 2
[/draft/draft-2.md][1000]
[/output/output-2.md][1000]
```

`[group: ...]` 是独立回退组；`[assistant]`、`[user]` 或 `[system]` 是配置身份，其中 `[system]` 输出时统一转为
`user`，避免普通消息之后的 system message 被部分 Provider 拒绝。下一行 Markdown title 原样写入消息；每个
`[/虚拟路径][字符数]` 是一个按位置排列的文件层。同一 group 的所有条目必须声明相同层数。第一层
始终作为基线，缺失时写入 `缺失`，不足字符数也不阻断后续条目。从第二层开始按顺序整组检查：只有该层全部文件
都存在、是 UTF-8 文本且达到各自字符数时才整组升级；遇到第一个不合格层就停止，不能跳到更高层。不同 group
独立选择层级，所以单层 cot 不参与 parts 的回退。配置中的文件全部不存在时不生成任何消息，也不改动 state。

插件读取 Deep Agents StateBackend 的当前 `state["files"]`，同时按 `ctx.paths.mapped` 读取当前 Agent 配置的 mapped
目录；虚拟路径必须是规范化绝对文件路径，不能用 `..` 或反斜杠越过映射边界。

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

Main Agent 的 `automation` 直接保存：

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
`ctx.vars`。Hook 插件返回的 Middleware 名称发生碰撞时，平台会按 Agent、binding 和返回序号为后续实例追加唯一
运行后缀，不要求不同插件使用不同 Python 类名；第一个原名仍保留 Deep Agents 的同名替换语义。
`enabled=false` 的 binding 不 import、不执行，也不因第三方依赖未准备而阻止请求。

Subagent 使用相同的直接列表结构，自行添加适用于该身份的 Hook 与周期 binding，不继承 Main Agent 的插件配置。
Main Agent 与 Subagent 的 Hook、上下文和插件自定义参数可以不同。同一个 Subagent profile 无论从 diamond 还是
显式递归到达，在一次请求中只有一个 Agent 身份上下文；每个周期 binding 最多有一个循环。每次 `task`
invocation 的 LangGraph state 仍然独立。

## ctx 与不可变原始消息

`ctx.request.messages` 是本次 OpenAI 请求通过权威校验并规范化后的 `messages[]`。OpenAI parts 已转为 LangChain
标准 blocks；API history 另行保留原始 wire。该对象是只读 tuple，每条消息、content 列表和嵌套 block 都递归只读：

- 同一请求的 prepare、Middleware、lifecycle、complete 和全部 Agent 身份看到相同内容；
- prepare 对 `ctx.messages` 的修改不会改变它；
- LangChain state 更新不会改变它；
- 下一次 API 请求根据客户端新提交的完整 messages 重新建立。

插件要稳定切分 Main Agent 用户信息时，应始终从 `ctx.request.messages` 开始计算，并为当前 Agent 建立可写深复制后
写入 `ctx.messages`；也可以使用 `agent_shell.automation.messages.mutable_request_messages()` 递归解冻容器。不要
原地修改只读 block，也不要把前序插件已经修改的工作列表当作原始事实。

平台不会把 image/audio/video/file 从消息中卸载到 `ctx.vars` 或资源区。`base64/url/file_id` 始终留在所属楼层
的 content block 中，也不存在资源 ID 自动补齐或 rehydrate。默认直通会保留这些叶子值；插件若主动落盘、替换
链接或生成新资产，必须自行把最终 block 放回返回的消息结构。

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

Main Agent 每次请求有一个 root invocation；每次实际 `task` 委派，包括同 profile 的并行、嵌套和递归调用，都会建立
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

## 权限、失败与一致性

自动化插件是实例维护者信任并安装的任意 Python 代码，以 Agent Shell 服务进程完整权限运行，没有 sandbox。
它可以访问网络、文件、进程、数据库和第三方服务。平台不限制业务副作用，也不提供事务、回滚、冲突协调或
强制超时。

prepare 或 Middleware 构造失败会阻止请求；LangChain Hook 的错误按 Agent graph 原生规则传播；lifecycle 错误
只停止对应循环；complete 错误只记录日志。平台不提供 `request_graph_stop()`，插件不能通过 Shell 私有信号接管
graph 终止条件。

插件必须有限返回，并自行保证外部操作一致性：数据库批量更新使用事务，文件先完整写临时文件再原子替换，
网络协议按服务端幂等规则设计。插件自己创建的线程、子进程或后台 Task 不归平台发现、等待或终止。
