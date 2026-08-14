# Workflow 输入上下文

Workflow 输入上下文是内置的 first-party LangChain Middleware。组件保存配置，Main Agent 或 Subagent 通过已有
capability refs 选择它；Subagent 通过现有继承、替换或关闭规则决定是否装配。组件内部没有第二个总开关。

## 字段

| 字段 | 说明 |
| --- | --- |
| `custom_transform_enabled` | 是否执行下方受信任 Python 函数。默认关闭。 |
| `custom_transform_source` | `def transform(read_file, config, workflow_state, agent_state, context): ...`，返回 partial Agent State update。`read_file` 读 Workflow 虚拟文件，`workflow_state` 是父图快照，`agent_state` 是私有 Agent State。 |
| `python_requirements` | 每行一个 PEP 508 外部依赖；修改后重启生效。 |
| `system_promote_enabled` / `system_promote_min_chars` | 是否把非顶部连续 system 中达到阈值的消息稳定上提；开关默认关闭，阈值默认 1,000,000 字符。 |
| `demote_non_top_system` | 上提后把仍不在顶部连续 system 区域的 system 改为 user；默认关闭。 |
| `slots` | 末尾追加的 role 槽位，支持 `user`、`assistant`、`system`。 |

消息规则固定先执行上提，再执行身份转换。若关闭上提、只开启身份转换，所有非顶部连续 system 消息都会转换为
user；阈值只参与上提判断。

每个 slot 可配置 `file`、按顺序排列的 `fallback_files`、`literal`、`max_chars`、`enabled` 和
`truncate_if_missing`。文件必须是 Workflow filesystem 的虚拟绝对路径。选择优先级是主文件、fallback 文件、
固定文本；空文件属于已找到的空内容。若所有来源都缺失且启用了截断屏障，则当前槽位不追加，并停止后续槽位。

## 信任边界

Python 源码在服务进程内执行，没有 sandbox；import 复用现有 Custom Middleware 依赖层，不建立新的依赖解析器。
不要把普通 API 请求字段当作不受信任脚本入口。`workflow_state` 与 `agent_state` 只供读取；需要更新的 channel
必须通过 transform 返回值交给 LangGraph reducer。原始 `WorkflowRuntimeContext.messages` 永远不被改写。
