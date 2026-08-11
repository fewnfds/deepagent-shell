# Workflow 输入上下文

Workflow 输入上下文是内置的 first-party LangChain Middleware。组件保存配置，Main Agent 或 Subagent 通过已有
capability refs 选择它；关闭组件或取消某个 `apply_to` 范围即可跳过。

## 字段

| 字段 | 说明 |
| --- | --- |
| `enabled` | 是否物化 Middleware。默认开启，但组件仍需被 Agent 引用。 |
| `apply_to` | `main_agent`、`subagent` 的执行范围；空数组表示不执行。 |
| `custom_transform_enabled` | 是否执行下方受信任 Python 函数。默认关闭。 |
| `custom_transform_source` | `def transform(messages, read_file, config): ...; return messages`。`messages` 是请求副本，`read_file` 读 Workflow 虚拟文件，`config` 是配置副本。 |
| `system_promote_enabled` / `system_promote_min_chars` | 是否把非顶部连续 system 中达到阈值的消息稳定上提。 |
| `demote_non_top_system` | 上提后把仍不在顶部连续 system 区域的 system 改为 user。 |
| `slots` | 末尾追加的 role 槽位，支持 `user`、`assistant`、`system`。 |

每个 slot 可配置 `file`、按顺序排列的 `fallback_files`、`literal`、`max_chars`、`enabled` 和
`truncate_if_missing`。文件必须是 Workflow filesystem 的虚拟绝对路径。选择优先级是主文件、fallback 文件、
固定文本；空文件属于已找到的空内容。若所有来源都缺失且启用了截断屏障，则当前槽位不追加，并停止后续槽位。

## 信任边界

Python 源码在服务进程内执行，没有 sandbox；import 复用现有 Custom Middleware 依赖层，不建立新的依赖解析器。
不要把普通 API 请求字段当作不受信任脚本入口。原始 `WorkflowRuntimeContext.messages` 永远不被改写，所有变换
只作用于本次 Agent invocation 的副本。
