# Workflow、Main Agent 与 Subagent

## Workflow

【Workflow】按父图和子图两个子页面管理同一种实体。当前 CRUD 保存名称、角色、说明、启用状态、一个共享 Filesystem、
可选准备与事件输出组件引用、`recursion_limit`（最大 super-step 数）、`execution_timeout_seconds`（单个 Run 总执行超时）和 `max_concurrency`（并行节点最大并发数），
以及一份当前 Graph definition/layout。
只有启用的父图出现在 `/v1/models`；子图不从 OpenAI-compatible 入口直接启动。两个页面复用同一配置表单和画布，
编辑器工具栏显示当前角色并返回对应列表。

Workflow root 不声明 `messages`。每个画布 Agent 节点由 wrapper 以空的私有 `messages` 调用自己的 Agent graph，
所以后继 Agent 不会自动继承前序对话。Agent 完成后，wrapper 把完整 reduced conversation 作为不可变 artifact 写入
Lifecycle/Run Store；父 State 的 `agent_invocations` 只保存 `invocation_id`、Workflow/Node/Agent 身份、`invoked_at` 和
`result_ref`。Task Dispatcher worker 的 State 引用只带 task identity，不重复 payload。Workflow Input Context 先从父 State
选择当前 checkpoint 可见的引用，再通过 `runtime.store` 读取、校验和转换完整 artifact。

并行分支读取同一个 LangGraph super-step snapshot，以不同 invocation ID 返回引用，不按开始时间、结束时间或 mapping
插入顺序解释先后。普通 Agent 的 State 索引按画布 Node、worker 按 Dispatcher Node + task ID 保留最新逻辑槽；旧 artifact
保留到 Lifecycle 清场，因此旧 checkpoint 的旧引用仍可读取。

后台 Run 管理不是画布 Node。每个 Run 的官方 Runtime Context 提供 `background_runs` 命令对象，Condition Router、Task Dispatcher、
Custom Tool、Middleware 或普通 Node 可以在自己的 invocation 内调用 `start_agent()`、`start_workflow()`、`check()`、`list()` 和
`cancel()`。启动命令立即返回 handle；查询不需要为了“检查状态”再走一个额外 Node。调用方负责把需要的 handle/snapshot 写入
`background_tasks` 或自己的 State channel，并自行编排循环、延时、retry 和结束条件。

启动必须提供稳定 `operation_id`；同一 caller Run 内因 Node retry 或重新执行而再次调用同一 operation 时返回原 handle，不会重复派遣。
该保证不跨 caller Run 或尚未实现的 Resume 边界；业务上确实需要重派时使用新的 operation ID。Workflow target 仍只允许已启用子图，后台 Agent 继承 caller Workflow Filesystem；后台输出不会自动混入
parent 响应。

【运行生命周期】页面按一次顶层请求列出 Lifecycle，显示后台任务、Checkpoint、Store 条目和动态目录计数。Lifecycle 的
messages、task records、resolved mapping records 和 parent/child checkpoint 默认持续保留，直到用户显式删除；删除时同时清理
受管的生命周期动态目录。父 Run 尚未终止，或仍有 `pending`、`running`、`cancel_requested` 后台任务时，删除返回冲突；必须等待
父 Run 终止，并先由 Workflow 代码、Tool/Middleware 或管理操作显式取消后台任务并使其进入终态。父图到达 End 不会隐式取消后台任务，也不会删除 Lifecycle。
删除开始后 Lifecycle 进入 `deleting`，不再接受新的后台 Run；清理失败时保留该状态，可由用户再次执行删除继续清场。

“生产 -> 审查 -> 重试”可以用于校验这些通用能力，但不是内置流程：Task Dispatcher 或普通控制流启动生产 Run，commands 查询
读取已完成项，Condition Router 根据用户自己的任务变量决定启动哪一个审查 Agent；审查不通过时再由 Router 回到用户自己的
重派路径，达到用户定义的次数后可以 Cancel 或 End。平台不理解“及格”“重试次数”或 Reviewer 身份，只提供 Run 事实和图编排原语。

【编辑 Flow】进入独立全屏 Vue Flow 页面。左右各有一条始终保留的工具图标轨；点击 active 图标只收起功能 panel，图标轨
不会消失。左侧提供组件库、元素追踪和问题：组件库提供当前角色允许的 Agent、条件路由和任务分发，可以点击或拖到画布；元素追踪列出当前全部 Node，
点击条目会保持当前缩放、把 Node 平滑移到视口中心并打开右侧属性；存在问题时问题图标显示红色数量角标，点击后在左侧列出
当前问题。右侧属性使用紧凑的 `key : value/control` 行，编辑所选 Node 或 Edge；空白点击会
清除选择并收起属性，平移、缩放和拖动不会触发收起，重新打开空选择属性时显示 Workflow 名称和 State contract。

选中连线后，可以选择两端共同支持的 Edge 类型、具体 source/target endpoint，也可以删除连线。Normal、Branch 与 Dispatch Edge 都
使用 Bezier 曲线；Branch/Dispatch key 在 Edge 属性中填写并保存，不显示在线段上，两种动态 Edge 仍以不同虚线、动画、箭头和端点名称区别。
问题列表显示当前阻止保存的原因；点击问题可以选中对应 Node、Edge 或 Workflow，画布底部不承载问题 UI。一个 Graph 最多保存 100 个 nodes
和 200 条 edges，同一个 Main Agent 可以被多个 Agent node 重复引用；normal 端点可以连接 `Start -> Agent`、
`Agent -> Agent` 和 `Agent -> End`，并允许一个端点连接多个激活方向。保存直接覆盖当前图，重新打开时恢复节点、边、位置
和 viewport；没有 draft/published revision、自动保存、并发编辑或恢复层。

保存入口允许不完整 draft。通过 `/v1/chat/completions` 运行时，Graph 必须至少包含一个 Start、一个 Agent 和一个 End，
并且每个节点都必须可从某个 Start 到达且能够继续到达某个 End；不满足时在 Agent 装配和 Graph compile 前返回 422。

画布 Start/End 分别映射 LangGraph 官方虚拟 `START/END`，不编译成 Shell 函数节点。Agent 节点引用的
`main_agent_id` 只保存在 Graph definition 中，不是 Workflow metadata 外键。`normal` 是节点端点类型；从 normal 输出
端点画到 normal 输入端点的线是一条具体连接，只表达后继节点的激活方向。Node 端点来自后端 Catalog 的 input/output
arrays，保存时仍只记录 `source_handle`/`target_handle`。多条 normal 出边按 LangGraph 官方 Graph API 激活多个后继节点；
父 Workflow State 是后端 contract，不作为画布变量节点或数据端口编辑。

任务分发节点引用一份配置独占的 `workflow-node/task-dispatcher` Python 包。它从当前 Workflow State/Runtime Context
生成运行时数量的任务，并由 compiler 转成 LangGraph `Send`；画布只保存一个 Dispatcher Node 和具名 Dispatch Edge，
不会保存 `n+m` 个临时 worker Node。同一个 Agent Node 可被不同 payload 多次调用，或由不同 `dispatch_key` 路由到不同
Agent Node。每次 worker 调用都在私有 Agent State 的 `workflow_task` 中得到任务，完成记录也保存该
task identity。完整配置与城市/乡镇示例见[任务分发](../wizard-pages/task-dispatcher-config.md)。

## Main Agent 与直接 Subagent

在【Agent / Main Agent】选择模型和输出模式等 capability。Main Agent 是完整 Agent 装配，由 Workflow 的
Agent node 引用。需要同步委派时，先创建 Subagent 实体，再由 Main Agent 按顺序保存 `subagent_id` 引用并选择委派
capability。

Filesystem 不再由 Main Agent 或 Subagent 选择；两处界面只显示锁定的“继承工作流”，且不会把这个显示值写入 payload。
每个 Main Agent 可以选择自己的 `filesystem-permissions`，Subagent 可以继承、替换或关闭该权限装配。权限配置同时控制
路径权限和该身份可见的文件工具；运行时由后端把 Workflow 的共享 Filesystem 与各身份权限组合并冻结。

Subagent settings 只定义身份、说明、capability 覆写和自己的有序 Middleware 引用。它没有 child 引用字段。当前固定为一层同步
`Main -> Subagent`，运行时使用 Deep Agents 官方 dictionary-based CompiledSubAgent。这是 Agent 内部
`SubAgentMiddleware`/`task` 能力，不决定外层 Workflow 的节点和边；多阶段、并行、条件和 join 属于后续 Workflow
图编辑器。

## 自定义 Middleware

Summarization 与 Prompt Caching 是两个独立组件。Main Agent 可以分别选择或不选择，Subagent 按 capability 的
继承/替换/关闭规则得到自己的最终配置；后端为每个身份显式物化官方 middleware，不依赖声明式 Subagent 自动继承
Main Agent 的 middleware 实例。

每个 Custom Middleware 组件只定义一个 Middleware。Main Agent 和 Subagent 各自保存有序 `middleware_refs`，列表顺序就是
多个用户 Middleware 的装配顺序，不走 capability 的继承/替换/关闭规则。Shell 只负责包加载并把官方 `AgentMiddleware` 实例交给
`create_deep_agent()`，不存在 prepare、周期循环或结束 Hook。

客户端 `messages[]` 是外围不可变请求事实，不会自动成为 Main Agent 活动消息。需要消息策略时，由 Middleware
在 `before_agent`/`abefore_agent` 中读取官方 state/context，按 Agent 身份整理后返回官方 state update。Main Agent
可用 `runtime.context.lifecycle_id` 从 `runtime.store` 读取冻结的 Lifecycle 输入；Subagent 默认保留 Deep Agents delegated messages，不自动附加根请求。格式见
[自定义 Middleware 包](middleware-packages.md)。

### Workflow 输入上下文 Middleware

Workflow Input Context 通过普通 Custom Middleware 的 `abefore_agent` 构造当前 Agent 私有消息。它没有专用 capability 或
装配槽位；从 `内置示例-workflow-input-context` 创建配置后，由 Main Agent 或 Subagent 的有序 `middleware_refs` 选择并排序。
Main Agent 可以从 Lifecycle Store 读取不可变请求快照，Subagent 默认使用 delegated messages；前序 Agent 输出和 Workflow 文件都必须由当前
WIC 代码显式选择。完整约定见[Workflow Input Context](workflow-input-context.md)。

WIC 可以读取 `state["workflow_task"]`，把当前任务材料编排进 worker 的私有 `messages`；它不负责认领任务、写入
`counting` 锁或调度其他 Agent。动态任务集合由 Task Dispatcher 在一个确定的 LangGraph Node invocation 中生成。

### 准备

Workflow 可绑定零或一个准备组件。Shell 先解析所有 Agent node 的纯配置装配，再把请求事实、Workflow
快照和按 node ID 组织的装配事实传给配置扩展中 `create_prepare()` 返回的 `async prepare(input)`。严格校验返回值后，
Shell 构造唯一最终 `WorkflowRuntimeContext`，再物化 Router/Dispatcher、Agent/Middleware 和 StateGraph。当前返回的
`context` 只从 `runtime.context.prepare` 读取；mutable graph state 仍由 LangGraph state/reducer 管理。Prepare 是外围能力，
不是 middleware 或 Graph node。

### 事件输出

Workflow 可绑定零或一个事件输出组件。它处理 `values`、`updates`、`custom` 等 Workflow-owned 非 Agent v3 事件；
每类事件由用户编写同步 `output(event)`，直接读取稳定 dict 和其中的原始 Python `data` 对象并返回字符串。不绑定时
这些事件不进入 OpenAI 响应。Agent Node 事件仍使用对应 Main Agent 的输出模式。完整字段见
[事件输出](../wizard-pages/workflow-event-output-config.md)。

## 校验与生效

Main Agent 与 Subagent 编辑页继续提交完整草稿给后端预校验，保存时再次校验。Workflow Graph PUT 接受当前画布
草稿；真实 Chat 请求从一次文件配置快照读取 Workflow 当前图、共享 Filesystem、Main Agent、Subagent、组件和
Provider secret view，完成 Agent 构造后关闭配置快照。图不能编译或装配失败时，本次请求直接失败。
