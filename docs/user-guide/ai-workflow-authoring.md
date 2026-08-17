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

`{kind}` 当前为 `middleware`、`workflow-prepare`、`condition-router` 或 `task-dispatcher`。节点和组件类型必须来自
catalog，不要靠模型记忆猜测。

执行写操作时遵守以下顺序：

1. 先复用语义匹配的现有组件；不要仅因名称不同就复制。
2. 新建依赖时由叶到根：组件 -> Subagent -> Main Agent -> Workflow -> Graph。
3. 新 Workflow 先保存为 `enabled: false`，Graph 和校验通过后再启用。
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

内置 WIC 已实现 Main Agent 读取本次 Lifecycle 原始消息、Subagent 保留委派消息。只有任务确实需要附件、消息裁剪、
前序 Agent 结果或 Dispatcher payload 时才修改其集中变化函数。详细边界见
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

先创建禁用的 parent Workflow：

```http
POST /api/workflows

{
  "name": "ai-workflow",
  "workflow_role": "parent",
  "description": "Processes a request with one configured Main Agent.",
  "filesystem_id": "<filesystem UUID>",
  "workflow_prepare_id": null,
  "workflow_event_output_id": null,
  "recursion_limit": 100,
  "execution_timeout_seconds": 600,
  "max_concurrency": 16,
  "enabled": false
}
```

再把以下 document PUT 到 `/api/workflows/{workflow-id}/graph`：

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

不要省略 `source_handle`、`target_handle`，也不要把 Vue Flow 自己的临时字段写进 document。Graph PUT 会校验 document
wire、Node config、handle 和拓扑 admission；`GET /api/validation/repository` 另行校验组件、Subagent 和 Main Agent 仓库，
当前不代替 Graph 运行校验。两处都通过后，GET Workflow，移除 `id`，把 `enabled` 改为 `true`，再 PUT
`/api/workflows/{workflow-id}`。

## 7. 当前每类 Node 的正式写法

以 `GET /api/workflow-node-catalog` 为当前事实。现有节点如下：

| Node | `config` | 输入 -> 输出 | 是否写脚本 |
| --- | --- | --- | --- |
| `start` | `{}` | 无 -> `next` | 否；直接映射 LangGraph `START` |
| `agent` | `main_agent_id`, `defer` | `in` -> `next` | Node 本身不写；行为来自 Main Agent、WIC 和组件 |
| `condition-router` | `condition_router_id` | `in` -> `branch` | 是；组件提供 `create_router()` |
| `task-dispatcher` | `task_dispatcher_id` | `in` -> `dispatch` | 是；组件提供 `create_dispatcher()` |
| `end` | `{}` | `in` -> 无 | 否；直接映射 LangGraph `END` |

### 7.1 Condition Router

Graph Node 只引用组件 UUID：

```json
{
  "id": "router",
  "type": "condition-router",
  "type_version": 1,
  "config": {"condition_router_id": "<condition-router UUID>"}
}
```

正式入口必须是同步工厂，返回固定的异步 callable：

```python
def create_router():
    async def route(state, runtime):
        shared_vars = state.get("shared_vars", {})
        branch = "review" if shared_vars.get("requires_review") is True else "otherwise"
        return {
            "activate": [branch],
            "update": {},
        }

    return route
```

Graph 中对应的候选边必须使用：

```json
{
  "id": "router-review",
  "source": "router",
  "source_handle": "branch",
  "target": "reviewer",
  "target_handle": "in",
  "branch_key": "review"
}
```

并显式连接唯一 `branch_key: "otherwise"`。`activate` 可以同时返回多个不同 key；空列表等价于 `otherwise`；
`otherwise` 不能和其他 key 同时激活。脚本只返回 Agent Shell contract，不 import 或返回 LangGraph `Command`，不返回
Node ID。`update` 只允许当前 Workflow State 已声明的顶层 channel。

### 7.2 Task Dispatcher

Graph Node 同样只引用组件 UUID：

```json
{
  "id": "dispatcher",
  "type": "task-dispatcher",
  "type_version": 1,
  "config": {"task_dispatcher_id": "<task-dispatcher UUID>"}
}
```

正式入口同样是同步工厂，返回异步 callable：

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

Graph 中对应的边使用 `source_handle: "dispatch"` 和 `dispatch_key: "item"`。每次调用必须产生 1–1000 个任务；
`task_id` 在本批唯一并来自稳定业务身份；`payload` 必须是严格 JSON object。脚本不 import 或返回 `Send`。空集合必须由
上游 Condition Router 绕过 Dispatcher，而不是返回空 `tasks`。

目标 worker 的 WIC 从私有 State 读取任务。基于内置 WIC 自定义时，保持原始消息复制逻辑，只在集中变化函数中加入：

```python
import json

# 放入 customize_context_messages(...) 中，接在现有
# user_messages = mutable_request_messages(request_messages) 之后。
task = state.get("workflow_task")
if isinstance(task, dict):
    user_messages.append(
        {
            "role": "user",
            "content": "Process this workflow task:\n"
            + json.dumps(task.get("payload", {}), ensure_ascii=False),
        }
    )
```

不要让多个 worker 扫描共享列表自行“抢任务”；Dispatcher 的 `Send` 已经为每个 worker 注入独立 task。

### 7.3 Agent Node

Agent Node 没有 Node script。它只引用完整 Main Agent。需要改变输入时写 WIC；需要调用外部能力时配置 Tool；需要改变
模型前后行为时配置 LangChain Middleware；需要同步委派时配置 Subagent。不要在画布上再造一个“Agent 脚本”层。

Agent 成功后，完整 reduced messages 写入 Lifecycle Store，父 State 只保留 `agent_invocations` 引用。后继 Agent 不会自动
继承前序消息；其 WIC 必须显式选择因果可见的 invocation，再按 `result_ref` 从 Store 读取 artifact。

### 7.4 Start 和 End

Start/End 没有脚本、配置或业务数据转换。Start 不把客户端消息注入 State；End 不负责自动取消后台任务、删除 Lifecycle
或拼接最终 Agent 内容。输入由 WIC 负责，输出由 Main Agent Output Mode 和可选 Workflow Event Output 负责。

## 8. 不是 Node、但可能需要写的脚本

### 8.1 Workflow Prepare

Prepare 是 Workflow-owned 外围组件，在 Graph 和 Agent 物化前运行一次，不是 Node 或 Middleware：

```python
def create_prepare():
    async def prepare(input):
        request = input["request"]
        return {
            "context": {
                "initial_message_count": len(request.get("messages", [])),
            }
        }

    return prepare
```

输入只有 JSON-compatible 的 `request`、`workflow`、`agents`；输出只能有 JSON-compatible `context`。运行时脚本通过
`runtime.context.prepare` 读取结果。Prepare 不返回 State update，不创建 LangGraph Node。

### 8.2 Agent Output Mode 与 Workflow Event Output

两者都是内联同步脚本，签名必须恰好为：

```python
def output(event):
    return event["message"]
```

Agent Output Mode 处理 Agent 事件；Workflow Event Output 只处理 Workflow-owned 非 Agent 事件。不要用它们修改 State、
做路由或隐藏顶层 HTTP error。应优先使用稳定的 `message`、`output`、`arguments`、`data_json` 字段；只有确实需要结构化
对象时才读取 `event["data"]`。

### 8.3 创建 Python package 脚本组件

Workflow Prepare、Condition Router、Task Dispatcher 和 Custom Middleware 都是配置独占 Python package。创建自定义
Router 的最小 body 形状如下；其他 package 类型只替换 endpoint 和 `main.py` contract：

```http
POST /api/blocks/condition-router

{
  "name": "Review router",
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

生产配置优先从经过审查的 template 创建；`__empty__` 只适合 AI 已经拥有完整、符合本文 contract 的源码时使用。
这些代码在服务进程的受信任边界执行，没有 sandbox。源码修改在下一次请求加载；`requirements.txt` 修改后必须重启。

## 9. 后台任务与多 Run 结构

Agent Shell 自己提供了一个单进程后台任务系统，但它不是 LangGraph Graph Node，也不是 Deep Agents 的
SubagentMiddleware。它通过当前 Run 的官方 `Runtime.context.background_runs` 暴露给 Condition Router、Task Dispatcher、
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
2. `GET /api/workflows/{id}/graph`，核对 UUID、handle、branch/dispatch key 和布局节点键。
3. 启用 parent Workflow。
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
- Condition Router 完整 contract：[条件路由](../wizard-pages/condition-router-config.md)
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
