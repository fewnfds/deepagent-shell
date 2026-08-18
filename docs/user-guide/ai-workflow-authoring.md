# AI 通过 Management API 装配 Workflow

本文是 AI 或自动化程序配置 Agent Shell 的首读入口。先完整读取本文，再按链接下钻字段细节。目标是通过
management API 创建一条真实、可运行的 Workflow，而不是直接修改 `data/config/` 中的 YAML。

本文只描述当前 Happy Path。API 返回值、稳定测试和根 `README.md` 是最终事实来源；`GET /openapi.json` 适合发现
HTTP endpoint，但部分配置写入接口使用通用 JSON body，不能替代本文和各组件 contract。

本文“正式写法”中的函数签名、返回结构和 Graph wire 是规范模板。`examples/` 中的业务案例只用于展示一种场景，
不能据此发明字段、跳过 catalog 或改变 Node contract。

## 1. 先理解四层对象

不要把以下对象混为一谈：

1. **组件**：模型、输出模式、Filesystem、系统提示词、Skill、权限、Custom Middleware，以及 Workflow 脚本组件。
2. **Agent 配置**：Main Agent 引用组件和 Subagent；Subagent 定义一层同步委派目标及 capability override。
3. **Workflow**：保存角色、Filesystem、运行限制，以及一份 Graph document。
4. **运行入口**：启用的 parent Workflow 名称才是 `/v1/chat/completions` 的 `model`；Main Agent 名称不是 model ID。

最小可运行链路是：

```text
Provider secret -> Model -----------+
                                      +-> Main Agent -> Agent node --+
Catalog default -> Output Mode -----+                              |
                                                                     +-> parent Workflow
Builtin example -> Input Context Middleware -> Main Agent ----------+       |
Filesystem ---------------------------------------------------------+       +-> /v1 model
Start ---------------------------------------------------------------Graph--+
End -----------------------------------------------------------------Graph--+
```

至少需要：一个 Filesystem、一个 Model、一个 Output Mode、一份 Workflow Input Context（WIC）Middleware、一个
Main Agent、一个 parent Workflow，以及 `Start -> Agent -> End` Graph。WIC 不能省略：客户端 `messages[]` 不会被平台
自动写进 Workflow root State；没有 WIC 时，画布 Agent 的初始私有 `messages` 为空。

## 2. Management API 登录

默认管理地址是 `http://127.0.0.1:19100`。`/api/*` 使用 management token；`/v1/*` 使用另一把 API Key，
两者不能互换。

默认 data root 下的 `data/config/agent-shell.env` 通常把 management token 写在第一行：

```dotenv
AGENT_SHELL_MANAGEMENT_TOKEN=<token>
```

自动化应按 key 查找，不要依赖行号，也不要把 token 打印到终端、日志、文档或请求正文。PowerShell 可以只把它保存在
当前进程变量中：

```powershell
$baseUrl = "http://127.0.0.1:19100"
$envFile = Join-Path (Get-Location) "data/config/agent-shell.env"
$tokenLine = Get-Content -LiteralPath $envFile |
    Where-Object { $_ -match '^AGENT_SHELL_MANAGEMENT_TOKEN=' } |
    Select-Object -First 1
if (-not $tokenLine) { throw "AGENT_SHELL_MANAGEMENT_TOKEN is missing" }
$managementToken = $tokenLine.Substring("AGENT_SHELL_MANAGEMENT_TOKEN=".Length)
$managementHeaders = @{ Authorization = "Bearer $managementToken" }

Invoke-RestMethod "$baseUrl/api/health"
Invoke-RestMethod "$baseUrl/api/readiness" -Headers $managementHeaders
```

若实例使用自定义 data root，应由操作者提供真实 `agent-shell.env` 路径。不能读取本机文件时，向操作者索取 management
token；不要尝试从页面、普通 API、DOM 或日志中找回 secret。

## 3. 修改前先发现当前事实

每次配置前至少读取：

| 请求 | 用途 |
| --- | --- |
| `GET /api/catalog` | 当前组件类型、必选标志、Subagent 策略和编辑器默认值 |
| `GET /api/workflow-node-catalog` | 当前 Node type/version、`config_schema`、input/output handle 和允许角色 |
| `GET /api/blocks/{type}` | 某类现有组件及 UUID |
| `GET /api/main-agents`、`GET /api/subagents` | 现有 Agent 配置 |
| `GET /api/workflows?workflow_role=parent` | 现有 parent Workflow |
| `GET /api/python-package-templates/{kind}` | 当前脚本模板和只读内置示例 |
| `GET /api/validation/repository` | 当前完整配置仓库诊断 |

`{kind}` 当前为 `middleware`、`command` 或 `task-dispatcher`。节点和组件类型必须来自
catalog，不要靠模型记忆猜测。

执行写操作时遵守以下顺序：

1. 先复用语义匹配的现有组件；不要仅因名称不同就复制。
2. 新建依赖时由叶到根：组件 -> Subagent -> Main Agent -> Workflow -> Graph。
3. 新 Workflow 先保存为 `enabled: false` 草稿；只有正式保存通过完整校验后才启用。
4. 保存每次 POST 返回的 UUID；引用永远使用 UUID，不使用显示名称。
5. PUT 是完整可写对象更新，不是 PATCH。普通对象可从 GET 结果移除 `id` 后修改；模型必须把 GET 返回的脱敏
   `credential` metadata 改为 `null`（同 Provider/Base URL 时保留旧 Key）或新的 write-only Key；Python package 组件还要
   移除 manifest、dependency status、error 等只读投影，只提交 `name`、`python_package` 和当前
   `python_package_files`。不要把 GET 投影不加检查地原样 PUT。
6. 422 时读取响应中的结构化 issue/path；不要盲目删除字段或降低约束。
7. 只要响应含 `X-Request-ID` 或 `request_id`，保留它用于诊断，但不要记录请求中的 secret 或用户正文。

## 4. 创建最小组件

### 4.1 Filesystem

最小 Filesystem 使用服务端默认工具配置：

```http
POST /api/blocks/filesystem
Authorization: Bearer <management token>
Content-Type: application/json

{"name":"AI workflow filesystem"}
```

保存响应中的 `id`。Filesystem 由 Workflow 引用，不进入 Main Agent 的 `capability_refs`。

### 4.2 Model

`credential` 是 management-only 的 write-only 输入。创建模型时在 HTTPS 或本机 loopback 连接中提交真实 Provider Key；
服务端会把它写入 `agent-shell.env` 的独立变量，并在模型 YAML 中只保存变量引用。响应不会回显明文。不要把 Key 写进
脚本、普通日志或后续 GET/PUT payload；编辑同一 Provider 与 Base URL 时传 `null` 会保留现有 Key。

```http
POST /api/blocks/model
Authorization: Bearer <management token>
Content-Type: application/json

{
  "name": "Primary model",
  "provider": "openai",
  "base_url": "https://api.openai.com/v1",
  "credential": "<write-only Provider API Key>",
  "model": "<current-model-id>",
  "provider_settings": {},
  "tool_choice": null,
  "response_format": null,
  "model_settings": {}
}
```

Provider 和 Provider-specific 字段以模型页面及后端校验为准。不要照抄示例中的 model ID；先确认实例当前可用模型。

### 4.3 Output Mode

Main Agent 必须引用完整 Output Mode。不要手写不完整的事件表；从 `GET /api/catalog` 复制
`editor_defaults.output_mode.default_value`，添加唯一 `name` 后提交到：

```http
POST /api/blocks/output-mode
```

若只需要最终 Assistant 文本，可以保留全部事件 key，但只启用 `assistant_text`：

```python
def output(event):
    return event["message"]
```

每个 `output_source` 必须恰好定义同步 `def output(event)` 并返回 `str`。完整八类事件及字段见
[输出模式](../wizard-pages/output-mode-config.md)。

### 4.4 Workflow Input Context Middleware

先请求：

```http
GET /api/python-package-templates/middleware
```

在 `catalog` 中按精确 `key == "内置示例-workflow-input-context"` 选择模板。使用该项返回的 `revision` 和 `files`
创建配置，不要从文档复制整份 WIC 源码：

```json
{
  "name": "Default workflow input context",
  "python_package": {
    "folder": "",
    "editable_files": ["main.py", "requirements.txt"]
  },
  "python_package_files": {
    "template_key": "内置示例-workflow-input-context",
    "revision": "<catalog revision>",
    "files": [
      {"path": "main.py", "content": "<main.py content returned by catalog>"},
      {"path": "requirements.txt", "content": "<requirements content returned by catalog>"}
    ]
  }
}
```

提交到 `POST /api/blocks/custom-middleware`。服务端生成独占 package folder；客户端不能自行填写 UUID folder。

内置 WIC 给出三项建议起点：Main Agent 读取本次 Lifecycle 原始消息、Subagent 保留委派消息、Dispatcher worker 把自己的
私有 task 加入上下文。它们不是强制的业务策略。当前 Agent 可以在
`build_workflow_input_messages(state, runtime, request_messages, backend)` 中按职责选择原始请求、私有 State、父图快照、
Dispatcher task、Runtime Context、Store 或 Workflow Filesystem 材料；不需要的默认步骤可以删除。详细边界见
[Workflow Input Context](workflow-input-context.md)。

## 5. 装配 Agent

### 5.1 Main Agent

最小 Main Agent 引用 Model、Output Mode 和 WIC：

```http
POST /api/main-agents
Authorization: Bearer <management token>
Content-Type: application/json

{
  "name": "Primary worker",
  "capability_refs": [
    {"type": "model", "block_id": "<model UUID>"},
    {"type": "output-mode", "block_id": "<output-mode UUID>"}
  ],
  "middleware_refs": [
    {"middleware_id": "<WIC UUID>"}
  ],
  "subagents": []
}
```

`middleware_refs` 有顺序：LangChain 的 `before_*` hook 正序执行，`after_*` 逆序执行，`wrap_*` 按列表嵌套。
多个 Middleware 会改写 `messages` 时，必须有意识地确定顺序。

### 5.2 可选 Subagent

Subagent 用于隔离复杂、长输出任务，不是画布 Node。先创建实体：

```http
POST /api/subagents

{
  "component_name": "Research specialist",
  "name": "researcher",
  "description": "Researches the delegated question and returns concise evidence with sources.",
  "settings": {
    "capability_overrides": [],
    "middleware_refs": []
  }
}
```

然后把 `{"subagent_id":"<UUID>"}` 加入 Main Agent 的 `subagents`。Subagent 默认继承 Main Agent 的可继承能力；只在
确有不同模型、提示、工具或权限时使用 `replace`/`disabled` override。Main Agent 还应引用 `subagent` 委派能力组件，
让 `task` 工具说明与路由提示符合当前业务。

Subagent 的 `name` 是模型可见路由名；`description` 应明确它何时被委派、负责什么、返回什么。不要创建层层嵌套的
Subagent 树，当前 contract 只支持 Main Agent 的一层直接 Subagent。

## 6. 创建 Workflow 和最小 Graph

先创建 parent Workflow。新建对象固定为草稿；请求中的 `enabled` 不能绕过正式保存：

```http
POST /api/workflows

{
  "name": "ai-workflow",
  "workflow_role": "parent",
  "description": "Processes a request with one configured Main Agent.",
  "filesystem_id": "<filesystem UUID>",
  "workflow_event_output_id": null,
  "recursion_limit": 100,
  "execution_timeout_seconds": 600,
  "max_concurrency": 16
}
```

再构造 Graph document。下面是最小正式图：

```json
{
  "definition": {
    "schema_version": 1,
    "state_contract": "agent-shell.workflow.agent-invocations.v1",
    "nodes": [
      {"id": "start", "type": "start", "type_version": 1, "config": {}},
      {
        "id": "worker",
        "type": "agent",
        "type_version": 1,
        "config": {"main_agent_id": "<main-agent UUID>", "defer": false}
      },
      {"id": "end", "type": "end", "type_version": 1, "config": {}}
    ],
    "edges": [
      {
        "id": "start-worker",
        "source": "start",
        "source_handle": "next",
        "target": "worker",
        "target_handle": "in"
      },
      {
        "id": "worker-end",
        "source": "worker",
        "source_handle": "next",
        "target": "end",
        "target_handle": "in"
      }
    ]
  },
  "layout": {
    "nodes": {
      "start": {"x": 80, "y": 160},
      "worker": {"x": 360, "y": 160},
      "end": {"x": 640, "y": 160}
    },
    "viewport": {"x": 0, "y": 0, "zoom": 1}
  }
}
```

不要省略 `source_handle`、`target_handle`，也不要把 Vue Flow 自己的临时字段写进 document。

同一个 Workflow 只保存这一份 Graph。草稿和正式对象在同一个列表中，以 `enabled=false/true` 区分；没有 revision、第二份
Graph 或第二个调度器。

保存 API：

```text
PUT  /api/workflows/{id}/draft     保存当前 document，并原子设置 enabled=false
POST /api/workflows/{id}/validate  只读返回当前候选 document 的完整正式校验报告
PUT  /api/workflows/{id}/graph     正式保存；完整校验通过后原子写入 document 和 enabled=true
GET  /api/workflows/{id}/graph     读取当前唯一 document
```

【保存草稿】不执行 Node Catalog admission、拓扑、引用或 Agent 装配校验。只要请求仍是 Graph document 的基础
`definition + layout` wire 且存储可写，就保存当前编辑状态；保存草稿也会把已正式发布的 Workflow 降回草稿，使它立即退出
`/v1/models` 和 child target 可用集合。Workflow 领域不设置 Node 数量、Edge 数量或 document 字节数配额；基础 HTTP、内存、
磁盘和 SQLite 仍可能按真实资源情况失败。

【正式保存】执行静态全量校验：wire、Node type/version/config、角色、Handle、Edge、拓扑、Command/Dispatcher 引用和 Main Agent
装配，以及 Command/Dispatcher 独占 Python package 的 folder、manifest、入口文件和静态 adapter contract。正式图必须恰有一个
Start 和一个 End，且 Start 至少有一条合法出边；`Start -> End` 合法。编辑器通过 `/validate` 预先显示全部 issue，并在存在
error、校验尚未完成或校验请求失败时禁用正式保存；请求失败会显示独立的重新校验操作。后端仍在正式 PUT 时重复相同校验，
不能绕过。正式失败不写候选 Graph，也不改变原 `enabled` 状态。

`admit_workflow_document()` 和 `validate_workflow_executable()` 都是静态校验；后者不是试运行，不会调用 Model、Command、Dispatcher
或 Agent，不 import 或执行用户 package。它在 admission 之上增加拓扑、引用、package 资源和静态 Agent 装配检查。
`GET /api/validation/repository` 校验整个配置仓库，也不代替
一次真实 Workflow 调用。

AI 通过 management FastAPI 调用 `/validate` 时能直接读取完整结构化问题，不需要打开 Vue Flow。响应包含 `valid`、`stage` 和
`issues[]`；每个 issue 至少提供 `code`、`severity`、`path`、`owner_id`、`owner_type`、`message_key`、`message_args` 和可读
`message`。读取全部 issue，不要只处理第一项；`severity=error` 阻止正式保存，warning 也应保留给操作者。请求本身失败不是一份
“无问题”报告：保持候选 Graph 不变，修复连接或服务状态后显式重试 `/validate`。

Workflow metadata PUT 只更新名称、角色、Filesystem 和运行限制，并保留当前 `enabled`；只有正式 Graph PUT 可以启用，草稿 PUT
可以停用。

## 7. 当前每类 Node 的正式写法

以 `GET /api/workflow-node-catalog` 为当前事实。现有节点如下：

本节代码分成两类信息：函数签名、返回字段、Edge key 和校验边界是固定 contract；读取哪个 State/Runtime 来源、采用什么
规则、是否更新 State、task 如何划分都只是建议示例。AI 应根据当前 Workflow 的真实数据流选择，不要把示例字段当成平台
字段。

| Node | `config` | 输入 -> 输出 | 是否写脚本 |
| --- | --- | --- | --- |
| `start` | `{}` | 无 -> `next` | 否；直接映射 LangGraph `START` |
| `agent` | `main_agent_id`, `defer` | `in` -> `next` | Node 本身不写；行为来自 Main Agent、WIC 和组件 |
| `command` | `command_id` | `in` -> `branch` | 是；组件提供 `create_command()` |
| `task-dispatcher` | `task_dispatcher_id` | `in` -> `dispatch` | 是；组件提供 `create_dispatcher()` |
| `end` | `{}` | `in` -> 无 | 否；直接映射 LangGraph `END` |

AI 画图时按以下顺序决定，不要从视觉布局反推运行语义：

1. 从 Catalog 选择 Node type/version，并严格按 `config_schema` 填 config。正式 Graph 恰有一个系统 `start` 和一个系统 `end`；
   不从组件库添加、复制或删除这两个系统节点。
2. 给每个业务 Node 分配全图唯一、稳定的 `id`。Node ID 以字母开头，只使用字母、数字、`_`、`-`，最长 64 字符。
3. 先画控制流，再写 layout。Start 至少连接一条合法出边；除系统 End 外，每个正式 Node 都必须从 Start 可达；End 自身允许没有入边。
4. 每条 Edge 从来源 Catalog output handle 指向目标接受该类型的 input handle。Edge `id` 同样唯一；不要省略两端 handle。
5. 来源 handle 决定协议：`next` 是 normal，`branch` 是 branch，`dispatch` 是 dispatch。不要在 wire 里另加 `edge_type`。
6. 最后检查 fan-out、fan-in、动态 key、叶子和循环退出，再调用 `/validate`。不要通过移动 Node、改颜色或添加 Vue Flow
   renderer 字段试图改变运行语义。

画布把其他来自 Start 的 Edge 显示为绿色，把进入 End 的 Edge 显示为红色；`Start -> End` 按 End 优先显示红色。其余 normal
Edge 为蓝色，branch/dispatch 保留自己的虚线与动画。颜色、class、marker 和 animation 都只是 Vue Flow 投影，不进入 Graph
document，也不改变 LangGraph 调度。

Node 做工作和 State update；Edge 表达激活。Command/Dispatcher 脚本只返回业务 key、task 和 update，不读取 Edge ID、目标 Node ID、
布局或全图拓扑。复杂业务优先拆成多个 Node + Edge，不创建同时拥有业务处理、路由、等待和终止语义的万能 Node。

每个来源只使用一种路由机制。普通 Agent/Start 使用 normal 静态 Edge；Command Node 的全部输出使用 branch Edge；Task
Dispatcher 的全部输出使用 dispatch Edge。不要给 Command/Dispatcher 追加 normal 出边，也不要让脚本直接返回 LangGraph
`Command`/`Send`；否则会把 Shell 的候选 Edge 映射与另一套动态路由混在一起。

### 7.1 Command Node

建议先从 `GET /api/python-package-templates/command` 读取
`内置示例-rule-based-command` 的当前 revision 和源码，再按业务改写；不要依赖文档中的代码副本。

Graph Node 只引用组件 UUID：

```json
{
  "id": "decision",
  "type": "command",
  "type_version": 1,
  "config": {"command_id": "<command UUID>"}
}
```

固定 contract 是同步工厂和返回结构；下面的字段、判断和 State 更新只是可替换示例：

```python
def create_command():
    async def command(state, runtime):
        shared_vars = state.get("shared_vars", {})
        branch = "review" if shared_vars.get("requires_review") is True else "continue"
        return {
            "activate": [branch],
            "update": {"shared_vars": {"last_route": branch}},
        }

    return command
```

Graph 中对应的候选边必须使用：

```json
{
  "id": "decision-review",
  "source": "decision",
  "source_handle": "branch",
  "target": "reviewer",
  "target_handle": "in",
  "branch_key": "review"
}
```

如果脚本可能返回 `continue`，再连接一条 `branch_key: "continue"` 候选边。`command` 可以按场景读取完整 `state`、
`runtime.context` 和 `runtime.store`；示例中的 `shared_vars.requires_review` 不是固定输入。`activate` 可以返回零个、一个或
多个不同 key；为空或省略时不激活后继，只提交 `update`，当前路径在该节点自然结束。Shell 不保留兜底 key，也不检查
脚本的条件是否穷尽；`if/elif/else`、`match` 和业务 key 全部由脚本负责。非空 key 必须完全匹配同源 Branch Edge，未知 key
使本次运行受控失败。`update` 可以更新当前 Workflow State 已声明的任意顶层 channel，不需要更新时返回 `{}`。脚本只返回
Agent Shell contract，不 import 或返回 LangGraph `Command`，不返回 Node ID。

### 7.2 Task Dispatcher

建议先从 `GET /api/python-package-templates/task-dispatcher` 读取
`内置示例-item-list-dispatcher` 的当前 revision 和源码，再按任务来源改写；`items` 只是示例，不是平台字段。

Graph Node 同样只引用组件 UUID：

```json
{
  "id": "dispatcher",
  "type": "task-dispatcher",
  "type_version": 1,
  "config": {"task_dispatcher_id": "<task-dispatcher UUID>"}
}
```

固定 contract 同样是同步工厂和返回结构。下面用 `shared_vars.items` 演示一种来源，不代表 Dispatcher 只能读取该字段：

```python
def create_dispatcher():
    async def dispatch(state, runtime):
        items = state.get("shared_vars", {}).get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("shared_vars.items must be a non-empty list")

        tasks = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise ValueError("each item must contain a stable string id")
            tasks.append(
                {
                    "task_id": f'item:{item["id"]}',
                    "dispatch_key": "item",
                    "payload": {"item": item},
                }
            )

        return {
            "tasks": tasks,
            "update": {"shared_vars": {"dispatched_count": len(tasks)}},
        }

    return dispatch
```

Graph 中对应的边使用 `source_handle: "dispatch"` 和 `dispatch_key: "item"`。`dispatch` 可以按业务需要从完整 `state`、
`runtime.context` 或 `runtime.store` 选择任务；任务来源、粒度、目标 key、payload 和父 State `update` 都由当前 Workflow
决定。每次调用必须产生 1–1000 个任务；`task_id` 在本批唯一并来自稳定业务身份；`payload` 必须是严格 JSON object；
`update` 可以更新任意已声明的顶层 State channel。脚本不 import 或返回 `Send`。

当前 contract 不接受空 `tasks`；如果数据可能为空，建议由上游 Command Node 绕过 Dispatcher。Agent Shell 会为每个
worker 注入独立 `workflow_task`，目标 Agent 是否读取、如何转换以及加入哪些 task 字段，仍由该 Agent 的 WIC 决定。内置
WIC 只提供一个可删除的默认转换。

### 7.3 Agent Node

Agent Node 没有 Node script。它只引用完整 Main Agent。需要改变输入时写 WIC；需要调用外部能力时配置 Tool；需要改变
模型前后行为时配置 LangChain Middleware；需要同步委派时配置 Subagent。不要在画布上再造一个“Agent 脚本”层。

Agent 成功后，完整 reduced messages 写入 Lifecycle Store，父 State 只保留 `agent_invocations` 引用。后继 Agent 不会自动
继承前序消息；其 WIC 必须显式选择因果可见的 invocation，再按 `result_ref` 从 Store 读取 artifact。

### 7.4 Start 和 End

Start/End 没有脚本、配置或业务数据转换。Start 不把客户端消息注入 State；End 不负责自动取消后台任务、删除 Lifecycle
或拼接最终 Agent 内容。输入由 WIC 负责，输出由 Main Agent Output Mode 和可选 Workflow Event Output 负责。

Start 是图入口，正式 Graph 必须恰有一个 Start 且至少有一条合法出边。每条 `Start -> target` 独立映射为
`add_edge(START, target)`；START 只在 Graph 启动时激活目标，不是普通业务 Node，也不参与 all-of。Vue Flow 画布始终提供恰好一个
系统 End，End 不作为普通 Node 供 AI 从 Node 列表添加。End 是 LangGraph `END` 的显式投影，不是普通 Node，也不是全图取消或
自动汇聚操作。End 可以没有任何入边。AI 可以让普通可达叶子自然结束；有循环时让退出路径连接 End，避免一直运行。

### 7.5 悬空叶子、End 与 super-step

LangGraph 按 super-step 执行。一个 super-step 中所有已调度 Node 读取同一边界 State snapshot；完成 update 在边界由 State reducer
合并，再产生下一步任务。Graph 在没有可执行任务、没有待传递消息时自然结束。

对当前 Agent Shell 图使用以下规则：

- 可达普通 Node 可以没有出边。它完成 update 后成为该路径的叶子，不再激活后继；其他活跃分支继续执行。
- 画布必须保留唯一系统 End，但 End 可以完全没有入边。没有 Node 需要证明自己能到达 End。
- 某条路径到达 End 只终止该路径，不取消同一步或其他分支，也不取消后台 Run。
- 全图仅在所有路径都不再产生任务时结束。叶子和 End 可以同时出现在同一张图中。
- 有环不等于有退出条件。环若始终产生下一步任务，会一直运行到用户逻辑退出、Run timeout 或 `recursion_limit`；建议让
  Command Node 的退出分支连接 End。

以下四种无循环连接方式在“何时全图没有剩余任务”上等价；每张画布仍有唯一 End，只是有些路径没有连接它。End 不会让尚在
运行的另一条路径提前停止：

```text
Start +-> A -> End       Start +-> A
      +-> B -> C -> End        +-> B -> C

Start +-> A -> End       Start +-> A
      +-> B -> C               +-> B -> C -> End
```

normal fan-out 与 fan-in 不是同一件事：

```text
fan-out:  A -> B       A 完成后同时激活 B、C
          A -> C

all-of:   B --+
              +-> J   J 只在 B、C 都完成后激活一次
          C --+
```

普通可执行目标 `J` 的多条非 START normal 入边会编译为 LangGraph 官方 `add_edge([B, C], J)` all-of waiting edge。若 B、C 来自互斥
条件而本次只激活一边，J 不执行；当其他路径也都结束后 Graph 正常结束，不会因一个永远不满足的 waiting edge卡住。
因此不要把互斥分支错误地汇聚到 all-of 目标。如果替代分支只需要结束，让它们分别成为叶子或分别指向 End。

START 是明确例外：

```text
Start -> J
Start -> A -> J
```

这里编译为 `add_edge(START, J)`、`add_edge(START, A)` 和 `add_edge(A, J)`；J 在启动时执行一次，A 完成后再执行一次，
不是等待 START 与 A 的 join。同理，`Start -> A -> B -> A` 可以直接表达循环入口：START 初始激活 A，B 的回边以后再次激活 A，
无需增加隔离 Start 的占位 Node。循环必须另有能停止继续激活的条件路径，通常由 Command 连接 End，并受 `recursion_limit` 兜底。

End 是例外，不是可执行 join Node：

```text
A -> End    编译为 add_edge(A, END)
B -> End    编译为 add_edge(B, END)
```

两条终止边互相独立；只要 A 到达就结束 A 路径，不等待 B。若业务确实要求 A、B 都完成后再作一次决策，应显式汇聚到实际
可执行 Node，再由它进入 End：

```text
A --normal--+
            +-> Command Node --branch_key=finish--> End
B --normal--+
```

这个 Command 的多 normal 入边就是明确的 all-of join；只有预期 A、B 在同一次运行都会激活时才这样画。Branch 只激活
`activate` 返回的候选 key；Dispatch 只为返回的 task 创建 worker；未选择的候选 Edge 不产生任务。

官方语义参考 [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) 和
[LangGraph super-steps](https://docs.langchain.com/oss/python/langgraph/checkpointers#super-steps)。

### 7.6 后续 Node type 的设计原则

增加 Node type 前先确认它能映射到 LangGraph 公开的 Node/Runnable、subgraph、`Command`、`Send` 或虚拟哨兵语义。不要为方便画布
实现第二套 super-step、Edge 触发、汇聚或终止规则。

Node 负责一次清晰工作以及 State/Runtime 的读取和更新；Edge 负责 Node 之间的激活关系。用户 Python package 不读取 Edge ID、
目标 Node ID、画布布局或完整拓扑，也不自行解释 Edge。Command/Dispatcher 只返回业务 key、update 或 task，Shell compiler 再机械
映射到画布声明的候选目标。

复杂逻辑优先拆成多个单一职责 Node，并通过 normal、branch 或 dispatch Edge 组合。只有无法用现有 Node + Edge 清楚表达、并且确实
对应一个完整官方运行范式时，才增加新 Node type；不要把业务处理、动态路由、等待、循环和汇聚塞进一个万能 Node。

## 8. 不是 Node、但可能需要写的脚本

### 8.1 Agent Output Mode 与 Workflow Event Output

两者都是内联同步脚本，签名必须恰好为：

```python
def output(event):
    return event["message"]
```

Agent Output Mode 处理 Agent 事件；Workflow Event Output 只处理 Workflow-owned 非 Agent 事件。不要用它们修改 State、
做路由或隐藏顶层 HTTP error。应优先使用稳定的 `message`、`output`、`arguments`、`data_json` 字段；只有确实需要结构化
对象时才读取 `event["data"]`。

### 8.2 创建 Python package 脚本组件

Command Node、Task Dispatcher 和 Custom Middleware 都是配置独占 Python package。创建自定义
Command 的最小 body 形状如下；其他 package 类型只替换 endpoint 和 `main.py` contract：

```http
POST /api/blocks/command

{
  "name": "Review command",
  "python_package": {
    "folder": "",
    "editable_files": ["main.py"]
  },
  "python_package_files": {
    "template_key": "__empty__",
    "revision": "",
    "files": [
      {"path": "main.py", "content": "<complete source>"}
    ]
  }
}
```

建议从经过审查的 template 创建；AI 已经拥有完整、符合本文 contract 的源码时也可以使用 `__empty__`。
这些代码在服务进程的受信任边界执行，没有 sandbox。源码修改在下一次请求加载；`requirements.txt` 修改后必须重启。

### 8.3 Python 库与可用能力

AI 能理解 Python 和常见库的用法，但不能仅凭模型知识判断当前 Agent Shell 实例实际安装了哪些包、版本是否兼容或某个
传递依赖是否会一直存在。当前 Management API 也没有“枚举所有可 import 模块”的 endpoint。按以下层次选择即可：

因此必须把“可用库”作为显式输入告诉 AI：先给它当前模板返回的 `python_requirements` 和文件内容；新增库时让它同时修改该
配置独占的 `requirements.txt`。不要只说“环境里应该有某库”，也不要要求 AI 猜宿主 Python。AI 可以根据库的官方 API 写代码，
但实例是否可 import 只能由 dependency status 和真实运行证明。

| 来源 | 如何使用 |
| --- | --- |
| Python 3.12 标准库 | 可以直接 import；建议能用标准库完成时不增加依赖 |
| 平台公开 contract | 模板所需的 `langchain`、`langchain_core`、`langgraph`、`deepagents` 及文档明确展示的 `agent_shell` helper 可以使用；只调用公开、已文档化的 API |
| 当前 package 的本地模块 | 使用正常相对 import，例如 `from .helpers import build_tasks` |
| 其他第三方库 | 在当前配置扩展的 `requirements.txt` 中声明直接依赖，再重启并验证 |

不要因为某个库恰好是 FastAPI、Provider 或其他核心包的传递依赖就直接使用，也不要让 AI 根据训练数据猜版本。新增第三方
能力前，建议让 AI 先确认该库支持 CPython 3.12、存在 Windows x64 wheel、与平台核心约束兼容，并在 `requirements.txt`
逐行写入普通 PyPI requirement。URL、本地路径、`.pth` 和只有源码发行包的依赖会被拒绝。

保存或 GET Python package 组件时，响应会投影：

- `dependency_status: "ready"`：当前 requirements 已准备完成，或没有额外依赖；
- `dependency_status: "restart_required"`：requirements 已变化，需要重启；
- `dependency_status: "failed"`：依赖解析或准备失败，结合 `dependency_error_code` 修正；
- `requirements_fingerprint`：当前依赖声明指纹，不是可用库清单。

依赖只从已启用 Workflow 可达的 Command、Dispatcher、Main Agent 和 Subagent 配置收集。最可靠的闭环是：声明直接依赖 ->
重启 -> GET 组件确认 `dependency_status` -> 调用一次真实 Workflow。AI 可以根据库的官方文档编写用法，但不能跳过这套实例
验证。

## 9. 后台任务与多 Run 结构

Agent Shell 自己提供了一个单进程后台任务系统，但它不是 LangGraph Graph Node，也不是 Deep Agents 的
SubagentMiddleware。它通过当前 Run 的官方 `Runtime.context.background_runs` 暴露给 Command Node、Task Dispatcher、
Custom Tool、Middleware 和普通 Node：

```python
commands = runtime.context.background_runs
handle = await commands.start_agent(
    "<target Main Agent UUID>",
    operation_id="review:item-42",
    shared_vars={"item_id": "42"},
)
snapshot = await commands.check([handle.task_id])
```

可用命令只有 `start_agent()`、`start_workflow()`、`check()`、`list()` 和 `cancel()`。`start_workflow()` 的 target 必须是已
启用的 child Workflow；后台 Agent 使用调用方 Workflow 的 Filesystem。命令立即返回 handle，调用方自己决定把 handle 或
snapshot 写入 `background_tasks`，以及如何轮询、等待、重试、汇总或结束。

### 9.1 何谓一次 Lifecycle、Run 和 Thread

一次外部 `/v1/chat/completions` 请求创建一个 **Lifecycle**，并拥有一个 parent Run/thread。该 Lifecycle 可以包含多个
后台 child Run：

```text
Lifecycle (共享输入、Store 与受管 Filesystem 生命周期)
├── parent Run / parent thread / parent checkpoint
├── background Agent Run / child thread
├── background Workflow Run / child thread
└── 每个 child 的 task record、状态和 checkpoint 摘要
```

每个 Run 都有独立的 `run_id`、`thread_id` 和 invocation 身份；后台 child 还带 `parent_run_id`、`launcher_id`、
`background_task_id` 和 `run_depth`。这些身份只能从官方 `Runtime.context` 读取，不能由脚本伪造，也不能把整个
Runtime/context/commands 写进 State 或 Store。

Lifecycle Store 保存本次请求的不可变输入、invocation artifact 和 task record；Workflow State 只保存路由所需的轻量引用。
独立后台 Run 不自动复制或合并父 Run 的 `messages`、State、checkpoint 或 Filesystem `files` channel。需要跨 Run 共享的
大材料应写入同一 Lifecycle 的受管 Filesystem 或官方 Store route，再由 child WIC/工具按引用读取；不能依靠内存变量或
State delta。

后台 child 的输出默认静默消费，不自动混入 parent 的 OpenAI 响应。只有 parent 通过 `check()`/`list()` 取得事实并显式把
结果写入自己的 State、Store 或输出策略时，结果才成为 parent 后续可见材料。

### 9.2 operation_id 与幂等

每次启动必须提供当前 caller Run 内稳定且不超过 128 字符的 `operation_id`。同一 Lifecycle、同一 caller Run、同一
operation ID 再次调用时返回原 task handle，不会重复派遣；若同 operation ID 改用另一个 target，返回冲突。该保证不跨
caller Run，也不跨尚未实现的 Resume；确实需要再次派遣时使用新的业务 operation ID。

不要把“后台 Run”误写成画布 Agent Node：后台 Agent 没有 `workflow_node_id`，但有实际 `agent_id`；后台 Workflow 也不
会出现在 parent Graph 的 Node catalog 中。不要用后台系统替代 Deep Agents 官方同步 Subagent，也不要用它替代
Task Dispatcher 在同一请求内通过 LangGraph `Send` 创建的动态 worker。

### 9.3 Lifecycle 管理 API

management API 只提供生命周期摘要和显式清场，不提供后台任务的通用外部启动 endpoint：

| 请求 | 作用 |
| --- | --- |
| `GET /api/workflow-lifecycles?page=1&page_size=10&query=` | 分页列出 Lifecycle、task 状态计数、Run/checkpoint/Store/filesystem 摘要 |
| `GET /api/workflow-lifecycles/{lifecycle_id}` | 获取一个 Lifecycle 摘要 |
| `DELETE /api/workflow-lifecycles/{lifecycle_id}` | 清理 parent/child Debug thread、Store prefix；active Run/task 时返回 409 |

删除时可选 `?delete_dynamic_directories=true` 清理本 Lifecycle 受管的动态目录。父 Run 到达 End 不会自动取消后台任务，
也不会自动删除 Lifecycle；必须先让后台 task 进入终态，再显式删除。Lifecycle 删除进入 `deleting` 后不再接受新的后台 Run，
清理失败时保留该状态以便继续清场。Lifecycle 摘要不返回 messages、Provider secret 或宿主路径。

## 10. 验证、启用和真实调用

配置完成后按有限清单验收：

1. `GET /api/validation/repository`，确认本次创建的组件和 Agent 没有 error。
2. `POST /api/workflows/{id}/validate` 提交候选 Graph，修正返回的全部 error。
3. `PUT /api/workflows/{id}/graph` 正式保存；返回成功后再用 GET 核对 UUID、handle、branch/dispatch key 和布局节点键。
4. 通过 `PUT /api/api-server` 设置独立 API Key；不要复用 management token：

```json
{
  "api_key": {"operation": "replace", "value": "<new printable ASCII key>"},
  "max_initial_messages": 1000
}
```

5. `POST /api/api-server/start`。
6. 使用 API Key 调用 `GET /v1/models`，确认 Workflow 名称出现。
7. 使用同一名称调用一次非流式 `/v1/chat/completions`，确认 Agent 真正收到任务并返回文本。

```http
POST /v1/chat/completions
Authorization: Bearer <API Key>
Content-Type: application/json

{
  "model": "ai-workflow",
  "messages": [
    {"role": "system", "content": "Follow the requested output format."},
    {"role": "user", "content": "Return exactly: workflow-ready"}
  ],
  "stream": false
}
```

不要仅以“配置保存成功”作为验收。Graph 引用、WIC、Provider、输出脚本只会在真实装配和运行链中全部闭合。

## 11. 何时下钻其他文档

- 所有组件及必选/继承策略：[创建组件](capabilities.md)
- Main Agent、Subagent、Workflow 语义：[Workflow、Main Agent 与 Subagent](configuration-workflow.md)
- WIC 与前序 invocation 读取：[Workflow Input Context](workflow-input-context.md)
- Python package、模板、依赖和加载：[文件化 Python 扩展](middleware-packages.md)
- Command 节点完整 contract：[Command 节点](../wizard-pages/command-config.md)
- Task Dispatcher 完整 contract：[任务分发](../wizard-pages/task-dispatcher-config.md)
- Output Mode 稳定事件字段：[输出模式](../wizard-pages/output-mode-config.md)
- Workflow Event Output 字段：[事件输出](../wizard-pages/workflow-event-output-config.md)
- OpenAI-compatible 运行入口：[API Server](api-server.md)
- 后台 Run、Lifecycle 清场与多 Run 语义：[Workflow、Main Agent 与 Subagent](configuration-workflow.md)
- Debug thread、checkpoint 与日志边界：[日志中心与 Workflow 观测](runtime-observability.md)
- secret 与远程访问边界：[安全与部署](../security-and-deployment.md)

Agent Shell 使用 Deep Agents 官方装配和 LangGraph Graph API。设计 Agent 时遵循官方上下文工程原则：始终相关的约定放在
精简提示中，任务特定材料由 WIC/Skill 按需加载；长且独立的工作委派给描述清晰的 Subagent；大结果放入共享
Filesystem 后按需读取。参考 [Deep Agents context engineering](https://docs.langchain.com/oss/python/deepagents/context-engineering)、
[Subagents](https://docs.langchain.com/oss/python/deepagents/subagents) 和
[Custom middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom)。
