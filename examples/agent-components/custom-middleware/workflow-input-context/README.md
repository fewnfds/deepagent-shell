# Workflow Input Context Middleware 示例

这是一个普通的 LangChain `AgentMiddleware` 示例，没有专用 WIC 组件或装配槽位。保存配置后，在 Main Agent
或 Subagent 的 `middleware_refs` 中选择它；多个 Middleware 的顺序完全由该列表决定。

`main.py` 默认完成两件事：

- Main Agent 用 `runtime.context.lifecycle_id` 从 `runtime.store` 取得 Workflow 原始输入，Subagent 保留自己的委派消息；
- 在 `build_workflow_input_context()` 中提供集中、可删除的附加文件和非顶部 system 转 user 功能。

## 修改位置

1. 在 `WIC_CONFIG["attachments"]` 中填写需要附加的 Workflow 虚拟文件。每项支持主路径、fallback、固定文本、
   role、字符上限和缺失时停止。
2. 需要把非顶部 system 消息转为 user 时，启用
   `WIC_CONFIG["convert_non_leading_system_to_user"]`。
3. 每个 WIC 对 Workflow 原始输入的选择、裁剪、重排和前序节点结果引用，都直接写在异步
   `customize_context_messages(state, runtime, request_messages)` 的标记位置。先从
   `state["workflow_state_snapshot"]["agent_invocations"]` 选择轻量引用，需要完整消息时调用示例的
   `load_invocation_artifact(runtime, record)`；该函数按当前 Lifecycle/Run 从官方 Store 读取不可变产物。
4. `build_workflow_input_context()` 集中保存附加文件和 system 转 user 两个通用功能区块；不需要时可以
   直接删除对应区块。

示例只实现异步 `abefore_agent`，因为 Agent Shell 的运行链使用异步调用。它通过工厂收到共享 filesystem
`backend`、Agent `scope` 和当前包 ID；运行时动态数据仍从 LangChain 官方 `state` 与 `runtime` 参数读取。

自定义 Middleware 是受信任的服务端 Python 代码，不在 sandbox 中运行。
