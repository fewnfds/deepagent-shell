# Workflow、Main Agent 与 Subagent

## Workflow

【Workflow】是 OpenAI-compatible `model` 的唯一来源。当前 CRUD 保存名称、说明、启用状态、一个共享 Filesystem、
可选 Workflow Prepare 引用，以及一份当前 Graph definition/layout。
只有启用的 Workflow 出现在 `/v1/models`。

Workflow root 不声明 `messages`。每个画布 Agent 节点由 wrapper 以空的私有 `messages` 调用自己的 Agent graph，
所以后继 Agent 不会自动继承前序对话。Agent 完成后，wrapper 把完整 reduced conversation 保存到父 State 的
`agent_invocations[invocation_id]`。每条记录只有 `invocation_id`、`workflow_id`、`workflow_node_id`、`agent_id`、
`invoked_at` 和 Agent graph 公开返回的标准 `messages`。Workflow Input Context 可以显式选择、校验和转换这些记录，
再构造当前 Agent 的初始消息。

并行分支读取同一个 LangGraph super-step snapshot，以不同 invocation ID 返回的记录由 reducer 合并，不按开始时间、
结束时间或 mapping 插入顺序解释先后。同一节点被再次调度时会产生独立 invocation ID，不覆盖先前执行。

【编辑 Flow】进入独立全屏 Vue Flow 页面。左侧组件库当前只有 Agent，可以点击或拖到画布；右侧属性栏编辑所选
Agent 的 Main Agent 引用并列出该 Node 声明的输入/输出端点。选中连线后，可以选择两端共同支持的 Edge 类型和具体
source/target endpoint，也可以删除连线；当前唯一选项是 Normal Edge。两侧均可独立收起。一个 Graph 最多保存 100 个
nodes 和 200 条 edges，同一个 Main Agent 可以被多个 Agent node 重复引用；normal 端点可以连接 `Start -> Agent`、
`Agent -> Agent` 和 `Agent -> End`，并允许一个
端点连接多个激活方向。保存直接覆盖当前图，重新打开时恢复节点、边、位置和 viewport；没有
draft/published revision、自动保存、并发编辑或恢复层。

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

Subagent settings 只定义身份、说明和 capability 覆写。它没有 child 引用字段。当前固定为一层同步
`Main -> Subagent`，运行时使用 Deep Agents 官方 dictionary-based CompiledSubAgent。这是 Agent 内部
`SubAgentMiddleware`/`task` 能力，不决定外层 Workflow 的节点和边；多阶段、并行、条件和 join 属于后续 Workflow
图编辑器。

## 自定义 Middleware

Summarization 与 Prompt Caching 是两个独立组件。Main Agent 可以分别选择或不选择，Subagent 按 capability 的
继承/替换/关闭规则得到自己的最终配置；后端为每个身份显式物化官方 middleware，不依赖声明式 Subagent 自动继承
Main Agent 的 middleware 实例。

Custom Middleware 组件保存有序 Middleware 包引用。Main Agent 选择组件后，直接 Subagent 按 capability 的
继承/替换/关闭规则得到自己的最终列表。Shell 只负责包加载并把官方 `AgentMiddleware` 实例交给
`create_deep_agent()`，不存在 prepare、周期循环或结束 Hook。

客户端 `messages[]` 是外围不可变请求事实，不会自动成为 Main Agent 活动消息。需要消息策略时，由 Middleware
在 `before_agent`/`abefore_agent` 中读取官方 state/context，按 Agent 身份整理后返回官方 state update。Main Agent
可读取冻结的 `runtime.context.messages`；Subagent 默认保留 Deep Agents delegated messages，不自动附加根请求。格式见
[自定义 Middleware 包](middleware-packages.md)。

### Workflow 输入上下文 Middleware

在 Components 中创建“Workflow 输入上下文”组件，再由 Main Agent 或 Subagent 的 capability refs 选择它。
它是独立源码目录中的内置实现，后端只负责固定物化；前端沿用本页的组件仓库和 Agent 覆写流程，不创建第二套
插件页面。

运行顺序是：选择 Main Agent 请求快照或 Subagent delegated messages -> 可选
`transform(read_file, config, workflow_state, agent_state, context)` -> 按字符阈值上提非顶部 system ->
把剩余非顶部 system 转为 user -> 顺序追加槽位。内部规划消息是本次调用的可变副本，`read_file` 只能读 Workflow backend
中的虚拟路径，`config` 是组件配置副本，`workflow_state` 是当前父图快照，`agent_state` 是当前私有 Agent State，
`context` 保存固定请求和当前 invocation 身份。transform 返回 partial Agent State update；其中 `messages` 用于本次
Agent 的私有对话。槽位按主文件、fallback 文件、literal 选择内容，再按 `max_chars` 截断；`truncate_if_missing` 会在全部来源
缺失时停止后续槽位。关闭组件或从该 Agent capability 装配中移除即可跳过，不影响
原始 `WorkflowRuntimeContext.messages`。

### Workflow Prepare

Workflow 可绑定零或一个 Workflow Prepare。Shell 先解析所有 Agent node 的纯配置装配，再把请求事实、Workflow
快照和按 node ID 组织的装配事实传给 `async def prepare(input)`。当前返回的 `context` 只从
`runtime.context.prepare` 读取；mutable graph state 仍由 LangGraph state/reducer 管理。

## 校验与生效

Main Agent 与 Subagent 编辑页继续提交完整草稿给后端预校验，保存时再次校验。Workflow Graph PUT 接受当前画布
草稿；真实 Chat 请求从一次文件配置快照读取 Workflow 当前图、共享 Filesystem、Main Agent、Subagent、组件和
Provider secret view，完成 Agent 构造后关闭配置快照。图不能编译或装配失败时，本次请求直接失败。
