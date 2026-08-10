# Workflow、Main Agent 与 Subagent

## Workflow

【Workflow】是 OpenAI-compatible `model` 的唯一来源。当前 CRUD 保存名称、说明、启用状态和一个共享 Filesystem，
以及一份当前 Graph definition/layout。只有启用的 Workflow 出现在 `/v1/models`。

【编辑 Flow】进入独立全屏 Vue Flow 页面。左侧组件库当前只有 Agent，可以点击或拖到画布；右侧属性栏编辑所选
Agent 的 Main Agent 引用并列出该 Node 声明的输入/输出端点。选中连线后，可以选择两端共同支持的 Edge 类型和具体
source/target endpoint，也可以删除连线；当前唯一选项是 Normal Edge。两侧均可独立收起。Agent 数量不限，同一个 Main Agent 可以被
多个 Agent node 重复引用；normal 端点可以连接 `Start -> Agent`、`Agent -> Agent` 和 `Agent -> End`，并允许一个
端点连接多个激活方向。保存直接覆盖当前图，重新打开时恢复节点、边、位置和 viewport；没有
draft/published revision、自动保存、并发编辑或恢复层。

画布 Start/End 分别映射 LangGraph 官方虚拟 `START/END`，不编译成 Shell 函数节点。Agent 节点引用的
`main_agent_id` 只保存在 Graph definition 中，不是 Workflow metadata 外键。`normal` 是节点端点类型；从 normal 输出
端点画到 normal 输入端点的线是一条具体连接，只表达后继节点的激活方向。Node 端点来自后端 Catalog 的 input/output
arrays，保存时仍只记录 `source_handle`/`target_handle`。多条 normal 出边按 LangGraph 官方 Graph API 激活多个后继节点；
共享 State 是 Workflow 级后端 contract，不作为画布变量节点或数据端口编辑。

## Main Agent 与直接 Subagent

在【Agent / Main Agent】选择模型和输出模式等 capability。Main Agent 是完整 Agent 装配，由 Workflow 的
Agent node 引用。需要同步委派时，先创建 Subagent 实体，再由 Main Agent 按顺序保存 `subagent_id` 引用并选择委派
capability。

Filesystem 不再由 Main Agent 或 Subagent 选择；两处界面只显示锁定的“继承工作流”，且不会把这个显示值写入 payload。
每个 Main Agent 可以选择自己的 `filesystem-permissions`，Subagent 可以继承、替换或关闭该权限装配。权限配置同时控制
路径权限和该身份可见的文件工具；运行时由后端把 Workflow 的共享 Filesystem 与各身份权限组合并冻结。

Subagent settings 只定义身份、说明和 capability 覆写。它没有 child 引用字段。当前固定为一层同步
`Main -> Subagent`，运行时使用 Deep Agents 官方 dictionary-based SubAgent。这是 Agent 内部
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
在 `before_agent`/`abefore_agent` 中读取 `ctx.request.messages` 并返回 state update。Subagent 默认保留 Deep Agents
delegated messages。格式见[自定义 Middleware 包](middleware-packages.md)。

## 校验与生效

Main Agent 与 Subagent 编辑页继续提交完整草稿给后端预校验，保存时再次校验。Workflow Graph PUT 接受当前画布
草稿；真实 Chat 请求从一次 SQLite 快照读取 Workflow 当前图、共享 Filesystem、Main Agent、Subagent、组件和
Provider secret view，完成 Agent 构造后关闭配置快照。图不能编译或装配失败时，本次请求直接失败。
