# 创建组件

【组件】提供十四类可复用配置。保存组件后，还要由 Workflow、Main Agent 或 Subagent 按各自所有权引用才会参与运行。

| 组件 | 用途 | Main Agent 要求 | Subagent 策略 |
| --- | --- | --- | --- |
| 模型 | Provider、模型名、凭据和请求设置 | 必选 | 继承或替换 |
| 系统提示词 | 基础 system prompt | 可选 | 继承、替换或关闭 |
| 文件系统 | Workflow 共享 workspace、映射、临时文件和文件工具 | Workflow 必选；Agent 不引用 | 锁定继承 Workflow |
| 文件系统权限 | 路径权限与文件工具、提示词覆写 | 可选 | 继承、替换或关闭 |
| 待办计划 | `write_todos` 与规划提示 | 可选 | 继承、替换或关闭 |
| 自定义工具 | 选择 `data/resources/custom_tools/` 中的工具 | 可选 | 继承、替换或关闭 |
| Skill | 选择 `data/resources/skills/` 中的 Skill | 可选 | 继承、替换或关闭 |
| 自定义 Middleware | 有序构造 LangChain Middleware | 可选 | 继承、替换或关闭 |
| 输出模式 | 把 v3 事件投影为响应文本 | 必选 | 只用于顶层 Main Agent |
| 异常重试 | Provider 或 ModelRetryMiddleware 重试 | 可选 | 继承、替换或关闭 |
| 委派能力 | 同步 Subagent 的提示与 `task` 说明 | 可选 | 只用于顶层 Main Agent |
| 上下文摘要 | `SummarizationMiddleware` 阈值、保留和工具参数截断 | 可选 | 继承、替换或关闭 |
| Prompt 缓存 | Anthropic prompt caching TTL 与最少消息数 | 可选 | 继承、替换或关闭 |
| Workflow 输入上下文 | 从请求 `messages[]` 整理初始消息，并按规则追加文件槽位 | 可选 | 继承、替换或关闭 |

组件编辑页从服务端 catalog 取得字段、默认值和资源发现结果。草稿校验与保存校验都以后端 contract
为准；记录使用 UUID 引用，重命名不会断开引用。

详细字段见[组件说明](../wizard-pages/README.md)。Agent 组合方式见
[装配 Main Agent 与 Subagent](configuration-workflow.md)。

自定义 Middleware 组件只保存有序包引用；包返回官方 LangChain `AgentMiddleware`。格式、安全边界和依赖管理见
[自定义 Middleware 包](middleware-packages.md)。

Workflow 输入上下文是一个内置但可替换的 first-party Middleware。它在 Agent invocation 的
`before_agent`/`abefore_agent` 中复制 `runtime.context.messages`，不会修改请求快照；Main Agent 和同步
Subagent 是否执行由组件的 `apply_to` 与现有 capability 引用共同决定。它支持受信任 Python 变换、system
消息上提/降级，以及从 Workflow 共享 filesystem 读取的 user/assistant/system 追加槽位。槽位只接受虚拟绝对路径，
依次使用主文件、fallback 文件和固定文本；启用截断屏障时，来源全部缺失会停止后续槽位。

自定义 Python 与现有 Custom Middleware 一样运行在服务进程的受信任边界内，没有 sandbox。`import` 只复用现有
Middleware 依赖层和核心已安装库，不新增第二套依赖解析器；管理员必须把这段源码视为可执行服务代码。
