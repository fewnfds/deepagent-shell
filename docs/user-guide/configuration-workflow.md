# Workflow、Main Agent 与 Subagent

## Workflow

【Workflow】是 OpenAI-compatible `model` 的唯一来源。当前 CRUD 保存名称、说明、启用状态、一个共享 Filesystem、
可选准备与事件输出组件引用，以及一份当前 Graph definition/layout。
只有启用的 Workflow 出现在 `/v1/models`。

Workflow root 不声明 `messages`。每个画布 Agent 节点由 wrapper 以空的私有 `messages` 调用自己的 Agent graph，
所以后继 Agent 不会自动继承前序对话。Agent 完成后，wrapper 把完整 reduced conversation 保存到父 State 的
`agent_invocations[invocation_id]`。每条记录只有 `invocation_id`、`workflow_id`、`workflow_node_id`、`agent_id`、
`invoked_at` 和 Agent graph 公开返回的标准 `messages`。Workflow Input Context 可以显式选择、校验和转换这些记录，
再构造当前 Agent 的初始消息。

并行分支读取同一个 LangGraph super-step snapshot，以不同 invocation ID 返回的记录由 reducer 合并，不按开始时间、
结束时间或 mapping 插入顺序解释先后。同一节点被再次调度时会产生独立 invocation ID，不覆盖先前执行。

【编辑 Flow】进入独立全屏 Vue Flow 页面。左右各有一条始终保留的工具图标轨；点击 active 图标只收起功能 panel，图标轨
不会消失。左侧组件库提供 Agent 与条件路由，可以点击或拖到画布；元素追踪列出当前全部 Node，点击条目会保持当前缩放、
把 Node 平滑移到视口中心并打开右侧属性。右侧属性使用紧凑的 `key : value/control` 行，编辑所选 Node 或 Edge；空白点击会
清除选择并收起属性，平移、缩放和拖动不会触发收起，重新打开空选择属性时显示 Workflow 名称和 State contract。

选中连线后，可以选择两端共同支持的 Edge 类型、具体 source/target endpoint，也可以删除连线。Normal 与 Branch Edge 都
使用 Bezier 曲线；Branch key 在 Edge 属性中填写并保存，不显示在线段上，Branch 仍以虚线、动画、箭头和端点名称区别。
画布底部问题条显示当前阻止保存的原因；点击问题可以选中对应 Node、Edge 或 Workflow。一个 Graph 最多保存 100 个 nodes
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
可读取冻结的 `runtime.context.messages`；Subagent 默认保留 Deep Agents delegated messages，不自动附加根请求。格式见
[自定义 Middleware 包](middleware-packages.md)。

### Workflow 输入上下文 Middleware

Workflow Input Context 通过普通 Custom Middleware 的 `abefore_agent` 构造当前 Agent 私有消息。它没有专用 capability 或
装配槽位；从 `内置示例-workflow-input-context` 创建配置后，由 Main Agent 或 Subagent 的有序 `middleware_refs` 选择并排序。
Main Agent 可以读取不可变的请求快照，Subagent 默认使用 delegated messages；前序 Agent 输出和 Workflow 文件都必须由当前
WIC 代码显式选择。完整约定见[Workflow Input Context](workflow-input-context.md)。

### 准备

Workflow 可绑定零或一个准备组件。Shell 先解析所有 Agent node 的纯配置装配，再把请求事实、Workflow
快照和按 node ID 组织的装配事实传给 `async def prepare(input)`。当前返回的 `context` 只从
`runtime.context.prepare` 读取；mutable graph state 仍由 LangGraph state/reducer 管理。

### 事件输出

Workflow 可绑定零或一个事件输出组件。它处理 `values`、`updates`、`custom` 等 Workflow-owned 非 Agent v3 事件；
每类事件由用户编写同步 `output(event)`，直接读取稳定 dict 和其中的原始 Python `data` 对象并返回字符串。不绑定时
这些事件不进入 OpenAI 响应。Agent Node 事件仍使用对应 Main Agent 的输出模式。完整字段见
[事件输出](../wizard-pages/workflow-event-output-config.md)。

## 校验与生效

Main Agent 与 Subagent 编辑页继续提交完整草稿给后端预校验，保存时再次校验。Workflow Graph PUT 接受当前画布
草稿；真实 Chat 请求从一次文件配置快照读取 Workflow 当前图、共享 Filesystem、Main Agent、Subagent、组件和
Provider secret view，完成 Agent 构造后关闭配置快照。图不能编译或装配失败时，本次请求直接失败。
