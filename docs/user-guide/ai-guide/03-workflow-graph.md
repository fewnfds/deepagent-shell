# 创建 Workflow Graph

## 创建 parent Workflow

parent Workflow 新建后固定处于草稿状态；请求中的 `enabled` 不会绕过正式保存：

```http
POST /api/workflows

{
  "name": "ai-workflow",
  "workflow_role": "parent",
  "description": "Runs the configured workflow nodes.",
  "workflow_event_output_id": null,
  "recursion_limit": 100,
  "execution_timeout_seconds": 600,
  "max_concurrency": 16
}
```

## 合法的最小拓扑

正式 Graph 的固定系统节点是唯一 Start 和唯一 End，不要求 Agent 或其他工作 Node。以下三种拓扑都合法：

```text
Start -> End

Start -> Work Node
End（没有入边）

Start -> Work Node -> End
```

可达普通工作 Node 没有出边时，该路径自然结束。一般 Workflow 仍建议包含完成业务所需的工作节点，并让需要明确退出的条件路径
显式连接 End。条件判断、State 更新和后继选择全部写在 Command Node 中，Graph 只声明候选连接。

下面是包含 Agent Node 的第三种拓扑的完整 Graph document。它是常见示例，不是正式 Graph 的最低要求：

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

`source_handle` 和 `target_handle` 是 Edge wire 的组成部分；Vue Flow 的临时字段不属于 Graph document。

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
装配，以及 Command/Dispatcher 独占 Python package 的 folder、manifest、入口文件和静态 adapter contract。正式图恰有一个
Start 和一个 End，且 Start 至少有一条合法出边；`Start -> End` 合法。编辑器通过 `/validate` 预先显示全部 issue，并在存在
error、校验尚未完成或校验请求失败时禁用正式保存；请求失败会显示独立的重新校验操作。后端在正式 PUT 时重复相同校验，
不存在绕过入口。正式失败不写候选 Graph，也不改变原 `enabled` 状态。

`admit_workflow_document()` 和 `validate_workflow_executable()` 都是静态校验；后者不是试运行，不会调用 Model、Command、Dispatcher
或 Agent，不 import 或执行用户 package。它在 admission 之上增加拓扑、引用、package 资源和静态 Agent 装配检查。
`GET /api/validation/repository` 校验整个配置仓库，也不代替一次真实 Workflow 调用。

AI 通过 management FastAPI 调用 `/validate` 时能直接读取完整结构化问题，不需要打开 Vue Flow。响应包含 `valid`、`stage` 和
`issues[]`；每个 issue 至少提供 `code`、`severity`、`path`、`owner_id`、`owner_type`、`message_key`、`message_args` 和可读
`message`。响应会一次返回全部 issue；`severity=error` 阻止正式保存，warning 保留给操作者。请求本身失败不是一份
“无问题”报告：保持候选 Graph 不变，修复连接或服务状态后显式重试 `/validate`。

Workflow metadata PUT 只更新名称、角色和运行限制，并保留当前 `enabled`；只有正式 Graph PUT 可以启用，草稿 PUT
可以停用。

## Node 和 Edge 规则

以 `GET /api/workflow-node-catalog` 为当前事实。现有节点如下：

本节代码分成两类信息：函数签名、返回字段、Edge key 和校验边界是固定 contract；读取哪个 State/Runtime 来源、采用什么
规则、是否更新 State、task 如何划分都只是建议示例。具体选择来自当前 Workflow 的真实数据流，示例字段不是平台字段。

| Node | `config` | 输入 -> 输出 | 是否写脚本 |
| --- | --- | --- | --- |
| `start` | `{}` | 无 -> `next` | 否；直接映射 LangGraph `START` |
| `agent` | `main_agent_id`, `defer` | `in` -> `next` | Node 本身不写；行为来自 Main Agent、WIC 和组件 |
| `command` | `command_id` | `in` -> `branch` | 是；组件提供 `create_command()` |
| `task-dispatcher` | `task_dispatcher_id` | `in` -> `dispatch` | 是；组件提供 `create_dispatcher()` |
| `end` | `{}` | `in` -> 无 | 否；直接映射 LangGraph `END` |

AI 画图时可按以下顺序组织；视觉布局不承载运行语义：

1. 从 Catalog 选择 Node type/version，并严格按 `config_schema` 填 config。正式 Graph 恰有一个系统 `start` 和一个系统 `end`；
   不从组件库添加、复制或删除这两个系统节点。
2. 给每个业务 Node 分配全图唯一、稳定的 `id`。Node ID 以字母开头，只使用字母、数字、`_`、`-`，最长 64 字符。
3. 控制流决定运行关系，layout 随后描述位置。Start 至少连接一条合法出边；除系统 End 外，每个正式 Node 都从 Start 可达；End 自身允许没有入边。
4. 每条 Edge 从来源 Catalog output handle 指向目标接受该类型的 input handle。Edge `id` 同样唯一，两端 handle 都是 wire 字段。
5. 来源 handle 决定协议：`next` 是 normal，`branch` 是 branch，`dispatch` 是 dispatch；wire 没有额外 `edge_type`。
6. fan-out、fan-in、Command 分支 key、Dispatcher task key、叶子和循环退出构成 `/validate` 前的结构检查。移动 Node、颜色和 Vue Flow
   renderer 字段都不会改变运行语义。

画布颜色、class、marker 和 animation 只是 Vue Flow 投影，不进入 Graph document，也不改变 LangGraph 调度。

Node 做工作和 State update；Edge 表达激活。Command/Dispatcher 脚本只返回业务 key、task 和 update，不读取 Edge ID、目标 Node ID、
布局或全图拓扑。多个单一职责的 Node + Edge 可以分别表达业务处理、路由、等待和终止语义。

普通 Agent/Start 使用 normal 静态 Edge。条件判断和后继选择全部由 Command Node 完成，其输出使用 branch Edge；Graph 只声明
候选目标。Task Dispatcher 专门生成并派发 task，其输出使用 dispatch Edge。Command/Dispatcher 没有 normal 输出 handle，
其脚本返回 Shell contract，而不是 LangGraph `Command`/`Send`。

## Command Node

`GET /api/python-package-templates/command` 返回
`内置示例-rule-based-command` 的当前 revision 和源码，可作为按业务改写的起点；文档代码不是当前模板副本。

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

Graph 中对应候选边的 wire 为：

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
脚本的条件是否穷尽；`if/elif/else`、`match` 和业务 key 全部由脚本负责。非空 key 与同源 Branch Edge 完全匹配，未知 key
使本次运行受控失败。`update` 可以更新当前 Workflow State 已声明的任意顶层 channel，不需要更新时返回 `{}`。脚本只返回
Agent Shell contract，不 import 或返回 LangGraph `Command`，不返回 Node ID。

## Task Dispatcher

`GET /api/python-package-templates/task-dispatcher` 提供
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
决定。当前 contract 接受每次调用产生的 1–1000 个任务；`task_id` 在本批唯一并来自稳定业务身份；`payload` 是严格 JSON object；
`update` 可以更新任意已声明的顶层 State channel。脚本不 import 或返回 `Send`。

当前 contract 不接受空 `tasks`；如果数据可能为空，建议由上游 Command Node 绕过 Dispatcher。Agent Shell 会为每个
worker 注入独立 `workflow_task`，目标 Agent 是否读取、如何转换以及加入哪些 task 字段，仍由该 Agent 的 WIC 决定。

## Agent、Start 和 End

Agent Node 没有 Node script。它只引用完整 Main Agent。需要改变输入时写 WIC；需要调用外部能力时配置 Tool；需要改变
模型前后行为由 LangChain Middleware 扩展，同步委派由 Subagent 提供。画布 Agent Node 本身没有额外“Agent 脚本”层。

Agent 成功后，完整 reduced messages 写入 Lifecycle Store，父 State 只保留 `agent_invocations` 引用。后继 Agent 不会自动
继承前序消息；其 WIC 通过选择因果可见的 invocation，再按 `result_ref` 从 Store 读取 artifact。

Start/End 没有脚本、配置或业务数据转换。Start 不把客户端消息注入 State；End 不负责自动取消后台任务、删除 Lifecycle
或拼接最终 Agent 内容。输入由 WIC 负责，输出由 Main Agent Output Mode 和可选 Workflow Event Output 负责。

Start 是图入口，正式 Graph 恰有一个 Start 且至少有一条合法出边。End 是 LangGraph `END` 的显式投影，不是普通 Node，
也不是全图取消或自动汇聚操作。End 可以没有任何入边。普通可达叶子可以自然结束；有循环时让退出路径连接 End。

## 叶子、汇聚与 super-step

LangGraph 按 super-step 执行。一个 super-step 中所有已调度 Node 读取同一边界 State snapshot；完成 update 在边界由 State reducer
合并，再产生下一步任务。Graph 在没有可执行任务、没有待传递消息时自然结束。

- 可达普通 Node 可以没有出边。它完成 update 后成为该路径的叶子，其他活跃分支继续执行。
- 画布保留唯一系统 End，但 End 可以完全没有入边。
- 某条路径到达 End 只终止该路径，不取消同一步、其他分支或后台 Run。
- 全图仅在所有路径都不再产生任务时结束。
- 有环不等于有退出条件。环若始终产生任务，会一直运行到用户逻辑退出、Run timeout 或 `recursion_limit`。

normal fan-out 与 fan-in 不同：

```text
fan-out:
A -> B
A -> C

all-of:
B -> J
C -> J
```

fan-out 表示 A 完成后同时激活 B、C。普通可执行目标 J 的多条非 START normal 入边会编译为
`add_edge([B, C], J)`；只有 B、C 都完成才激活 J。若 B、C 来自互斥条件而本次只激活一边，J 不执行。
互斥分支适合作为独立叶子或分别指向 End，而不是汇聚到 all-of 目标。

START 是例外：`Start -> J` 与 `Start -> A -> J` 会让 J 分别在启动时和 A 完成后各执行一次，不是等待 START 与 A 的 join。
多条进入 End 的边也互相独立；End 不等待所有来源。需要 A、B 都完成后再决策时，先让两者汇聚到一个真实可执行 Node，
再由该 Node 进入 End。

Branch 只激活 `activate` 返回的候选 key；Dispatch 只为返回的 task 创建 worker；未选择的候选 Edge 不产生任务。

官方语义参考 [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) 和
[LangGraph super-steps](https://docs.langchain.com/oss/python/langgraph/checkpointers#super-steps)。

## 新 Node type 的边界

新 Node type 以 LangGraph 公开的 Node/Runnable、subgraph、`Command`、`Send` 或虚拟哨兵语义为映射基础。
第二套 super-step、Edge 触发、汇聚或终止规则不属于当前架构。

Node 负责一次清晰工作以及 State/Runtime 的读取和更新；Edge 负责 Node 之间的激活关系。用户 Python package 不读取 Edge ID、
目标 Node ID、画布布局或完整拓扑，也不自行解释 Edge。复杂逻辑可以拆成多个单一职责 Node；新 Node type 对应现有
Node + Edge 无法清楚表达的官方运行范式。

下一步：[编写 Python 扩展](04-python-extensions.md)。
