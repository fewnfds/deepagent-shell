# AI Workflow 编写指南

本目录汇总 AI 或自动化程序通过 Management API 配置 Agent Shell 时所需的入口。
OpenAPI 中的通用 JSON body 不表达各组件的完整字段；当前事实来自 API 返回值、稳定测试和根 `README.md`。

## 软件如何完成一次 Workflow 请求

Agent Shell 是 Workflow-first 的 LangGraph/Deep Agents 配置与运行外壳。Management API 负责创建组件、Agent 和 Workflow；
`POST /v1/chat/completions` 只运行已经启用的 parent Workflow，请求的 `model` 与该 Workflow 的 name 相等时才能匹配。

```text
OpenAI-compatible messages[]
  -> 按 Workflow name 捕获一次配置快照
  -> 创建 Lifecycle、Run 和 thread 身份并冻结原始输入
  -> 物化 Command、Task Dispatcher、Main Agent、Subagent 和 Middleware
  -> 编译并执行 Workflow StateGraph
  -> 消费 LangGraph stream events v3
  -> Agent Output Mode / Workflow Event Output 投影
  -> 按事件顺序组成一次用户输出
```

### 输入与 Agent 上下文

客户端 `messages[]` 只作为本次 Lifecycle 的不可变输入保存，不自动写入 Workflow root State，也不跨请求累积成产品聊天历史。
每个 Agent Node 启动时，由它装配的 WIC `before_agent`/`abefore_agent` 从 Runtime Store、当前私有 State、Dispatcher task、
前序 invocation 或 Filesystem 中选择材料，并构造该 Agent 独有的标准多轮消息。不同 Agent 不会自动共享整包输入或前序消息。

### Workflow 执行主线

Start 激活第一个工作 Node；Agent Node 运行完整 Main Agent，Command Node 返回 State update 和 branch key，Task Dispatcher 返回
State update 和通过 `Send` 派发的 tasks。Node 返回值驱动 Workflow State 和后继路由。Agent 完成后，完整 reduced messages
写入 Lifecycle Store，Workflow State 的 `agent_invocations` 只保存可供后继读取的身份和结果引用。End 或没有后继的可达叶子
结束当前路径。

### 输出事件投影

运行器使用 LangGraph `astream_events(version="v3")` 观察 Workflow、Agent、模型、Tool 和用户 Python 产生的事件。事件不会
自动改写 Workflow State：

- Agent Node 内的事件按来源归属该 Main Agent，由它的 Output Mode 投影；
- Workflow-owned 事件由 Workflow 可选绑定的 Event Output 投影；
- Command/Task Dispatcher 可在运行期用 `get_stream_writer()` 主动写出 `custom` 事件；
- 每个启用的 `output(event)` 返回一个字符串，运行器按事件顺序组成用户输出；未启用或返回空字符串的事件不输出。

Node 的 State/路由返回值与输出事件是两条独立通道。输出事件只用于单向展示，不向产生事件的 Node 返回处理结果。具体 Python
用法见[编写 Python 扩展](04-python-extensions.md)，事件字段见[输出模式](../../wizard-pages/output-mode-config.md)和
[事件输出](../../wizard-pages/workflow-event-output-config.md)。

## 最小 Graph 事实

正式 Graph 的结构包含唯一 Start 和唯一 End。下面两种结构都合法：

```text
Start -> Work Node（End 保留在 Graph 中，可以没有入边）

Start -> Work Node -> End
```

Work Node 可以是当前 Node catalog 中允许的工作节点。可达工作节点没有出边时，默认为隐式连接 end 自然结束。
一般 Workflow 可按业务放入实际需要的工作节点，条件判断和后继选择由 Command Node 表达。
循环等需要明确退出条件的路径使用显式 End 连接。
Model、Output Mode、Main Agent 和 Workflow Input Context（WIC）Middleware 只在使用 Agent Node 时出现。
客户端 `messages[]` 不会自动写入 Workflow root State；WIC 负责为每个 Agent 单独构造输入上下文。

## 组件建议

向用户建议自行创建 model、filesystem

## 阅读顺序

首次创建完整 Workflow 时，从第一章开始，再按实际使用的 Node 选择章节：

1. [登录、对象关系与事实发现](01-api-and-discovery.md)
2. [创建 Filesystem 并按需装配 Agent](02-components-and-agents.md)
3. [创建 Workflow Graph](03-workflow-graph.md)
4. [编写 Python 扩展](04-python-extensions.md)
5. [使用后台 Run](05-background-runs.md)（仅使用后台任务时阅读）
6. [验证、启用和真实调用](06-validation-and-references.md)

修改已有对象时，第一章提供 PUT 和事实发现规则，目标对象所在章节提供领域字段。
Python 扩展目录、依赖与直接文件维护规则集中在第四章；其他章节的片段不是完整 package contract。

本文只描述当前 Happy Path。示例中的函数签名、返回结构和 Graph wire 是规范模板；业务字段和判断规则只是示例。
`examples/` 只展示示例场景，不是新增字段、替代 catalog 或改变 Node contract 的依据。
