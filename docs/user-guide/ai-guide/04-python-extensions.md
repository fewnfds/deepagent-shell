# 编写 Python extension

本章覆盖 Custom Tool、Agent Event Output、Workflow Event Output、Command、Task Dispatcher 和 Custom Middleware 的 file-based Python package，以及 instance directory 和 dependency 规则。

## Event output package

Agent Event Output 与 Workflow Event Output 都使用 configuration-owned Python package，固定 signature 为：

```python
def output(event):
    if event["event_type"] == "assistant_text":
        return event["message"]
    return ""
```

每个 package 只有这一份 entry；在同一函数内按 `event_type` 分支。Agent Event Output 处理 Agent event；Workflow Event Output 只处理 Workflow-owned non-Agent event。它们不承担 State update、
routing 或 top-level HTTP error handling。稳定的 `message`、`output`、`arguments`、`data_json` field 适合常规 output；
`event["data"]` 用于确实需要结构化对象的场景。

Runtime 会把所属范围内的每种 `event_type` 交给同一个 `output(event)`；读取 `tool_name`、`status`、`channel` 等事件专属 field 前，
必须先判断 `event_type`，未选择的分支返回 `""`。空字符串只过滤最终渲染文本，不改变完整 block 合并或 Agent tool call/outcome 配对。

## 创建 file-based Python package

Custom Tool、Command Node、Task Dispatcher、Custom Middleware 和两类 Event Output 都使用 configuration-owned Python package。创建 Event Output 的最小 body
如下；只需替换 endpoint 和 `main.py` contract：

```http
POST /api/blocks/agent-event-output

{
  "name": "Review command",
  "python_package": {
    "folder": "",
    "editable_files": ["main.py", "requirements.txt"]
  },
  "python_package_files": {
    "template_key": "__empty__",
    "revision": "",
    "files": [
      {"path": "main.py", "content": "<complete source>"},
      {"path": "requirements.txt", "content": ""}
    ]
  }
}
```

Workflow Event Output 使用 `POST /api/blocks/workflow-event-output`。建议从对应 template catalog 创建；AI 已经拥有完整且符合
contract 的 source 时也可以使用 `__empty__`。

首次保存后，系统会把 template 复制到该 configuration 独占的 extension directory：

```text
data/config/python_package_instances/
  command/<configuration-uuid>/
  task-dispatcher/<configuration-uuid>/
  agent-tool/<configuration-uuid>/
  agent-middleware/<configuration-uuid>/
  agent-event-output/<configuration-uuid>/
  workflow-event-output/<configuration-uuid>/
```

frontend 和 Management API 只是创建、查看及保存这些 file 的入口，不是唯一修改入口。创建完成后，可以直接在对应 instance directory 中维护
`main.py`、`requirements.txt`、local module 和 test file；不必为了修改 extension source 而改动 `frontend/`。直接新增的 local file 可以使用
relative import；把 package-relative path 加入 editor file list 后，该 file 也会显示在 component editor 中。

`requirements.txt` 是扩展生成时应一并提供的可见文件；内容为空表示该 extension 没有额外 third-party dependency。内置示例和 `__empty__`
模板都提供这个空文件。只有当 source import 了平台核心之外的 package 时，AI 才应在同一 package 中填写或修改
`requirements.txt`，逐行写入普通 PyPI requirement，并在 `editable_files` 与 `python_package_files.files` 中一起提交该文件。

不要修改 Agent Shell 管理的 `package.json`，也不要移动、重命名 extension directory，或让一个 configuration 引用另一个 configuration 的 directory。

这些 code 在 service process 的 trusted boundary 执行，没有 sandbox。Python source change 会在下一次请求时重新加载；`requirements.txt` change 在
service restart 后生效。component editor page 若早于 external change 打开，其 revision 会过期；reload 后才能从页面保存，否则服务端拒绝覆盖。

Custom Tool 固定使用同步无参 `create_tool()`，并返回一个 LangChain `BaseTool`；推荐返回 `@tool` 装饰后的函数。Command 和 Task Dispatcher 的 factory、return structure 及 Edge key 见[创建 Workflow Graph](03-workflow-graph.md)。Custom Middleware
factory 的 return type 是官方 LangChain `AgentMiddleware`；完整 contract 见[File-based Python extension](../middleware-packages.md)。

## 从 Workflow Node 写出 event

Command 的 `command(state, runtime)` 和 Task Dispatcher 的 `dispatch(state, runtime)` 可以在执行过程中调用 LangGraph
`get_stream_writer()`，写入一次或多次 output event，不必等到 Node return。唯一的权威示例是
[`内置示例-rule-based-command`](../../../examples/workflow-components/command/rule-based-command/main.py)，其中的写法是：

```python
from langgraph.config import get_stream_writer

get_stream_writer()(f"Command selected branch {branch}.\n")
```

同样的 call 可以写在 `dispatch(state, runtime)` 中。只在 runtime callable 内获取 writer；不要在 module top level、
`create_command()`/`create_dispatcher()` factory 或 `output(event)` 中调用，也不要在 Node return 后继续使用 writer。

Agent Shell 通过 LangGraph `astream_events(version="v3")` 消费这些数据。`get_stream_writer()` 写入的数据在 v3 stream 中是
`custom` event；Command/Task Dispatcher 属于 Workflow，因此由 Workflow 绑定的 Workflow Event Output component 中 `custom` 对应的
`output(event)` 进行 projection。Agent Node 内 Tool 或 Middleware 写出的 `custom` event 则由该 Agent 的 Agent Event Output projection。

Workflow Event Output 的 `custom` branch 可以直接把 string event 交给用户：

```python
def output(event):
    data = event["data"]
    return data if isinstance(data, str) else ""
```

只有 Workflow 绑定 Workflow Event Output 且 `output(event)` 对 `custom` 返回非空字符串时，event 才进入响应；其他情况下 event 仍由 Runtime 消费。
event 是单向 output，Node 不会收到 projection result。field 说明见[Workflow Event Output](../../wizard-pages/workflow-event-output-config.md)。

Workflow Event Output 的内置示例继续使用 HTML `details` 格式，并覆盖 `custom`、`lifecycle`、`values`、`updates`、`tasks`、
`checkpoints`、`input`、`input.requested`、`debug` 和 `other`。这些类别仍由当前 v3 normalizer 产生；统一 package 只是把原来每类
独立的脚本合并到同一个 `output(event)` 分支中。旧版默认只把 `custom` 和 `lifecycle` 投影到公开文本，其余类别默认关闭是为了
避免 State、checkpoint、task 和 debug 数据直接进入响应；当前示例把分支全部列出，用户可按需返回字符串。

## Runtime capability 与 discovery path

Python extension 的可用 capability 取决于 caller 和 invocation stage。entry function 的 public type 是继续查找 LangChain、LangGraph 和
Deep Agents 用法的起点：

| script entry | 当前 runtime stage 与 public object | 可继续发现的 capability |
| --- | --- | --- |
| `command(state, runtime)` / `dispatch(state, runtime)` | LangGraph Node；`state` 与 `langgraph.runtime.Runtime` | State、`runtime.context`、`runtime.store`、custom stream、execution identity，以及 Shell Context 中的 background Run command |
| Custom Tool callable | LangChain Tool；Tool argument 与可选 `ToolRuntime` | Agent State、Runtime Context、Store、custom stream 和 Tool return value |
| `AgentMiddleware` runtime hook | LangChain Agent Middleware；hook 的 `state`、`runtime` 或 `request` | Agent lifecycle、Model request、Tool call、State update 和 custom stream |
| `create_tool()` | Agent construction stage；同步无参 factory | 返回一个 `BaseTool`；Tool invocation 的 Runtime 能力写在 Tool callable 参数中，不注入 factory |
| `create_command()` / `create_dispatcher()` / `create_middleware()` | request-scoped construction stage | Shell 提供的 factory argument 和 local package；此时还没有 Node/Tool Runtime |
| Agent Event Output / Workflow Event Output 的 `output(event)` | Agent Shell output projection stage；稳定 `event` dict | event filtering 与 string rendering；不处于 LangGraph Node Runtime |

capability 有三层来源：

- **Agent Shell contract**：本指南、component page、source 和稳定测试明确给出的 object、field 与 return structure；
- **official API capability**：上述 public type 在当前 LangChain/LangGraph/Deep Agents version 提供的 API；
- **Python environment**：standard library、当前 package 的 local module 和显式声明的 third-party dependency。

capability discovery 通常从“public type name + target action”开始。在当前开发环境中，已注册的 `langchain-docs` MCP 提供官方文档搜索；
例如 `LangGraph Runtime store`、`LangGraph get_stream_writer custom data`、`LangChain ToolRuntime state context`、
`LangChain AgentMiddleware wrap_tool_call`。常用官方入口包括
[LangGraph Node and Runtime](https://docs.langchain.com/oss/python/langgraph/graph-api#nodes)、
[LangChain Runtime](https://docs.langchain.com/oss/python/langchain/runtime)、
[LangGraph custom data](https://docs.langchain.com/oss/python/langgraph/streaming#custom-data)和
[LangChain Middleware](https://docs.langchain.com/oss/python/langchain/middleware/overview)。

一次具体 capability 判断可以按以下 evidence 收敛：

1. 从本章和对应 package contract 确认 script entry、runtime stage 及 injected object；
2. 从[开发与版本](../../development-and-release.md)确认当前 locked version；
3. 用 public type 和 target action 查询 official docs，得到官方推荐用法；
4. 对照 Shell return contract、当前 source 或稳定测试，确认该 official capability 在本 entry 中确实可达；
5. third-party library 再结合 `python_requirements`、dependency status 和一次真实 Run 确认实例中可用。

官方 type 上存在但尚未写入 Shell contract 的 attribute 属于 inherited capability，不自动成为产品承诺。Shell 自己的 return structure 仍覆盖通用官方
示例：例如 Command/Task Dispatcher 返回 `activate`、`tasks` 和 `update`，由 compiler 映射为 LangGraph `Command`/`Send`，
extension 本身不直接返回这两个 object。仓库只保留一份可运行的权威示例，其他 capability 通过 type、官方文档和实际 contract 继续发现。

## Python library 与 available capability

AI 能理解 Python 和常见 library 的用法，但不能仅凭 Model knowledge 判断当前 Agent Shell 实例实际安装了哪些 package、version 是否兼容，或某个
transitive dependency 是否会一直存在。当前 Management API 也没有 enumerate-all-importable-modules endpoint。

available library 的可靠 input 包括当前 template 返回的 `python_requirements`、file content 和 configuration-owned `requirements.txt`。
“environment 中应该有某个 library”或 Model 对 host Python 的猜测不能证明该 library 可用。AI 可以根据 library 的 official API 写 code，
实例是否可 import 则由 dependency status 和真实 Run 证明。

| 来源 | 如何使用 |
| --- | --- |
| Python 3.12 standard library | 可以直接 import；能用 standard library 完成时不增加 dependency |
| platform public contract | template 所需的 `langchain`、`langchain_core`、`langgraph`、`deepagents` 及文档明确展示的 `agent_shell` helper 可以使用；public documented API 构成 stable usage |
| 当前 package 的 local module | 使用 normal relative import，例如 `from .helpers import build_tasks` |
| 其他 third-party library | 在当前 configuration extension 的 `requirements.txt` 中声明 direct dependency，再 restart 并验证 |

FastAPI、Provider 或其他 core package 带来的 transitive dependency 不是 extension 的 stable dependency declaration。third-party capability 的可用条件包括支持 CPython 3.12、
提供 Windows x64 wheel、与平台核心约束兼容，并在 `requirements.txt` 中逐行声明普通 PyPI requirement。
URL、local path、`.pth` 和只有 source distribution 的 dependency 会被拒绝。

保存或 GET Python package component 时，响应包含以下 projection：

- `dependency_status: "ready"`：当前 requirements 已准备完成，或没有额外 dependency；
- `dependency_status: "restart_required"`：requirements 已变化，需要重启；
- `dependency_status: "failed"`：dependency resolution 或 preparation 失败，结合 `dependency_error_code` 修正；
- `requirements_fingerprint`：当前 dependency declaration fingerprint，不是 available library list。

dependency 只从 enabled Workflow 可达的 Command、Task Dispatcher、Main Agent 和 Subagent configuration 收集。最可靠的闭环是：声明 direct dependency ->
restart -> GET component 确认 `dependency_status` -> invoke 一次真实 Workflow。library 的 official docs 说明用法，这套实例 evidence 说明它在当前 environment 可用。

因此 AI 编写 Workflow 时可以理解并处理依赖：先根据实际 import 判断是否需要 third-party package；不需要时保持 `requirements.txt` 为空，
需要时将 direct dependency 和源码作为同一份 package payload 保存。不能因为某个 package 被核心 runtime 间接安装，就省略自己的依赖声明。

下一步：[使用 background Run](05-background-runs.md)覆盖 asynchronous subtask；[Validation、enabled 与真实 invocation](06-validation-and-references.md)
覆盖普通 Workflow 的完成阶段。
