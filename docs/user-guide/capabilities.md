# 创建组件

【组件】提供当前 catalog 声明的可复用配置。保存组件后，还要由 Workflow、Main Agent 或 Subagent 按各自所有权引用才会参与运行。

| 组件 | 用途 | Main Agent 要求 | Subagent 策略 |
| --- | --- | --- | --- |
| 模型 | Provider、模型名、凭据和请求设置 | 必选 | 继承或替换 |
| 系统提示词 | 基础 system prompt | 可选 | 继承、替换或关闭 |
| 文件系统 | Workflow 共享 workspace、映射、临时文件和文件工具 | Workflow 必选；Agent 不引用 | 锁定继承 Workflow |
| 文件系统权限 | 路径权限与文件工具、提示词覆写 | 可选 | 继承、替换或关闭 |
| 待办计划 | `write_todos` 与规划提示 | 可选 | 继承、替换或关闭 |
| 自定义工具 | 选择 `data/resources/custom_tools/` 中的工具 | 可选 | 继承、替换或关闭 |
| Skill | 选择 `data/resources/skills/` 中的 Skill | 可选 | 继承、替换或关闭 |
| 自定义 Middleware | 定义一个 LangChain Middleware | 通过有序引用装配 | Subagent 独立有序引用 |
| 输出模式 | 把 v3 事件投影为响应文本 | 必选 | 只用于顶层 Main Agent |
| 异常重试 | Provider 或 ModelRetryMiddleware 重试 | 可选 | 继承、替换或关闭 |
| 委派能力 | 同步 Subagent 的提示与 `task` 说明 | 可选 | 只用于顶层 Main Agent |
| 上下文摘要 | `SummarizationMiddleware` 阈值、保留和工具参数截断 | 可选 | 继承、替换或关闭 |
| Prompt 缓存 | Anthropic prompt caching TTL 与最少消息数 | 可选 | 继承、替换或关闭 |
| Workflow 输入上下文 | 从请求 `messages[]` 整理初始消息，并按规则追加文件槽位 | 可选 | 继承、替换或关闭 |
| 准备 | 在 LangChain 构造前准备本次 Workflow 的静态 runtime context | Workflow 可选绑定 | 不属于 Agent capability |
| 事件输出 | 用 Python 把 Workflow-owned v3 事件投影为响应字符串 | Workflow 可选绑定 | 不属于 Agent capability |
| 条件路由 | 读取完整 Workflow State/Context，更新 State 并激活具名 Branch Edge | 画布 Node 引用 | 不属于 Agent capability |

组件编辑页从服务端 catalog 取得字段、默认值和资源发现结果。草稿校验与保存校验都以后端 contract
为准；记录使用 UUID 引用，重命名不会断开引用。

详细字段见[组件说明](../wizard-pages/README.md)。Agent 组合方式见
[装配 Main Agent 与 Subagent](configuration-workflow.md)。

自定义 Middleware 组件保存一个配置独占的 Python 扩展引用，并只返回一个官方 LangChain `AgentMiddleware`。Main Agent 和
Subagent 分别通过有序 `middleware_refs` 装配多个配置。格式、安全边界和依赖管理见
[自定义 Middleware 扩展](middleware-packages.md)。

Workflow 输入上下文是一个内置但可替换的 first-party Middleware。它在 Agent invocation 的
`before_agent`/`abefore_agent` 中规划当前私有 Agent 的初始消息，不会修改请求快照；Main Agent 默认使用
`runtime.context.messages`，同步 Subagent 默认使用官方 task tool 传入的 delegated messages。两者是否执行只由现有
capability 引用及继承/替换/关闭规则决定。它支持受信任 Python 变换、system
消息上提/降级，以及从 Workflow 共享 filesystem 读取的 user/assistant/system 追加槽位。槽位只接受虚拟绝对路径，
依次使用主文件、fallback 文件和固定文本；启用截断屏障时，来源全部缺失会停止后续槽位。

每个画布 Agent wrapper 在 Main Agent graph 成功完成后，把公开返回的完整 reduced messages 写入父 Workflow State 的
`agent_invocations`。记录包含 invocation、Workflow、画布节点和 Agent 身份以及首次调用时间；同一节点再次调度时使用
独立 invocation。同步 Subagent 仍由 Deep Agents 官方 Middleware 在 Main Agent 内部调度，不建立隐藏归档 wrapper。
这条父子 State 输出映射不需要额外的结束 Hook 或 Recorder 组件。

准备是 Workflow-owned 组件。它在所有 Agent 配置解析完成后、任何模型/Middleware/Agent/StateGraph
构造前执行一次 `async def prepare(input)`；当前只允许返回 `{"context": {...}}`，结果冻结到
`runtime.context.prepare`。它不属于 Main Agent/Subagent capability，也不是通用生命周期 Hook。

事件输出也是 Workflow-owned 组件。Workflow 通过 UUID 可选绑定一份配置；各事件的同步 `output(event)` 读取稳定
dict，返回值必须是字符串。它只控制 Workflow-owned 非 Agent 事件的 OpenAI 响应投影，不改变 checkpoint、Debug、
最终 State 或 Agent 自己的输出模式。字段和 Python 对象类型见[事件输出](../wizard-pages/workflow-event-output-config.md)。

条件路由组件保存一个 `workflow-node/condition-router` Python 扩展引用和普通 config。扩展通过同步
`create_router()` 工厂物化 `async route(state, context)`；用户在画布 Branch Edge 上直接填写分支 key，route 通过
`activate` 返回一个或多个完全匹配的 key，并可通过 `update` 返回 State 局部更新，空列表使用必须显式连接的 `otherwise`。
完整 package 和返回契约见[条件路由](../wizard-pages/condition-router-config.md)。

这些自定义 Python 都运行在服务进程的受信任边界内，没有 sandbox。自定义 Middleware 和 Condition Router 从分类静态模板
创建配置独占的 Python 扩展，并在扩展目录可选的 `requirements.txt` 声明外部包；模板本身不运行也不参与依赖。Workflow Prepare 和
Workflow 输入上下文变换目前仍在组件配置中保存源码与 `python_requirements`。生效配置共享启动期扩展依赖层。
requirements 修改后重启生效；文件化扩展源码在下一次请求重新加载，仍为内联形式的组件源码按各自组件说明生效。
