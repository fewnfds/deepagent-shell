# Workflow Input Context Middleware

这是 Workflow Agent 的可修改输入模板。默认实现三项常见策略：

1. Main Agent 从当前 Lifecycle Store 读取本次请求的原始 `messages[]`；
2. Subagent 保留父 Agent 通过 `task` 委派给它的私有消息；
3. Task Dispatcher worker 把自己的 `workflow_task` 追加为一条 user 消息。

这三项是建议起点，不是强制策略。WIC 可以按当前 Agent 的职责从原始请求、私有 State、父图快照、Dispatcher task、
Runtime Context、Store 或 Workflow Filesystem 中选择材料。模板通过官方 `AgentMiddleware.abefore_agent` 更新当前 Agent 的
私有 `messages`，不把整包原始输入写入 Workflow root State。

## 唯一业务修改点

把当前 Workflow 特有的消息选择、裁剪、重排和前序结果加载写在
`build_workflow_input_messages(state, runtime, request_messages, backend)` 中。默认先复制并校验原始消息，再加入当前 worker
task；可以删除、替换或扩展这些步骤。

读取前序 Agent 结果时：

1. 从 `state["workflow_state_snapshot"]["agent_invocations"]` 中按明确的 Node 或 task 身份选择记录；
2. 调用 `load_invocation_artifact(runtime, record)` 读取该记录指向的完整 artifact；
3. 只把当前 Agent 真正需要的内容加入 `messages`。

不要依赖 `agent_invocations` 的插入顺序，也不要自动加入所有前序 Agent 的完整消息。

## Imports 与依赖

`json` 和 `typing` 来自 Python 标准库；`langchain`、`langchain_core`、`langgraph` 与 `agent_shell` imports 是这个适配器的
平台 contract。模板不需要第三方 `requirements.txt`。只有新增其他直接依赖时才填写 requirements，并在重启后确认依赖状态。

这是受信任的服务端 Python 代码，不在 sandbox 中运行。
