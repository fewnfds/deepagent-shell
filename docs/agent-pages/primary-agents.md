# Primary Agent

Primary 保存一份加法式装配：

```json
{
  "name": "writer",
  "capability_refs": [
    {"type": "model", "block_id": "UUID"},
    {"type": "output-mode", "block_id": "UUID"}
  ],
  "subagents": [],
  "workers": []
}
```

## 能力引用

页面顺序为模型、系统提示词、文件系统、待办计划、自定义工具、Skill、自定义 Middleware、输出
模式、异常重试、提示词预设、Subagent、Context Worker 委派。每个 type 最多一项
`{type, block_id}`；未出现就是不装配。

模型和输出模式由 manifest 标为必需，页面没有“不装配”或清除选项，右侧草稿校验区
会逐项检查，管理 API 也拒绝缺少任一项的配置。filesystem 和其他能力可选；未选择 filesystem 时
不构造其 Middleware，模型没有 `read_file`。配置选择器和摘要只显示名称，
服务端 payload 与删除保护仍只认 UUID。

## Subagent binding

每条 binding 保存：

- `name`：父 Agent 调用 task 时使用的唯一标识；
- `description`：告诉父 Agent 何时委派；
- `subagent_override_id`：可选的覆写策略 UUID；空字符串表示完整继承当前 Primary。

binding 的名称必须匹配 `[A-Za-z_][A-Za-z0-9_-]*`，同一 Primary 内唯一，说明必填；
添加 binding 即启用，未完成的 binding 应直接移除。非空覆写 UUID 会参与删除保护。

运行时使用：

```text
当前 Primary 的 capability_refs
+ 可选 Subagent capability_overrides
- output mode、Prompt Preset、两类委派能力与当前 Primary 自身 bindings
= 一个 raw synchronous Subagent
```

Subagent 不能选择其他 Primary。filesystem 在当前 Primary 选择时固定继承，不提供覆写入口；
同一次请求内 Primary 与全部同步 Subagent 共享请求级临时文件 state。未选择时 Subagent 仍可运行，
但没有 filesystem 工具。当前不自动添加 general-purpose，不支持
异步、dynamic 或 CompiledSubAgent。

## Context Worker binding

每条 `workers[]` binding 保存：

- `name`：`run_worker` 的可选 Worker 枚举值，在当前 Primary 内唯一；
- `description`：告诉 Primary 何时使用该 Worker；
- `worker_profile_id`：必填 Worker Profile UUID。

只有 Primary 装配 Context Worker 委派组件时才创建 `run_worker` Tool，并要求至少一条有效 binding。
模型可以在同一个响应中发出多个 `run_worker` 调用；LangChain ToolNode 执行并把各自结果作为独立
ToolMessage 交还 Primary。每个 Worker 是完整 `create_deep_agent()` graph，使用冻结客户端消息副本和自己的
Prompt Preset，不继承 Primary 已经产生的 AI/Tool 过程。DeepAgents Subagent binding 与 Worker
binding 互相独立，可分别或同时使用。

## 保存与运行

桌面宽度下，右侧草稿校验区占页面三分之一；窄屏下恢复为整行。校验区展示后端对当前完整草稿的结构与
静态装配报告；连续输入停止 1000ms 后刷新，离散选择可立即刷新，晚到的旧响应不会覆盖新草稿。错误行
包含具体 owner、字段 path 和原因。保存按钮不把最近报告当作授权，服务端保存与真实请求共享同一个静态装配
校验，不能由直接 API 调用绕过 required、引用、依赖、最终 Subagent/Worker 或静态工具名规则。最终公开
工具名在 Primary 与每个 Subagent/Worker 各自的 `create_deep_agent()` 前检查，重名会以稳定 422 拒绝，不再
静默覆盖。磁盘资源、Python 构造、依赖安装和 Provider 等运行现场问题仍在真实请求中检查。
保存失败会一次展示后端报告中的全部问题，并按当前中文/英文语言格式化；成功保存后，该 Primary 名称会在 API Server
通过静态门禁并处于 running 时成为 `/v1/models` 中的公开 model ID。
运行中的每个新请求都会从同一份请求级数据库快照解析该公开名称、Primary UUID 和全部装配；保存、
改名或删除只影响之后捕获快照的请求，不改写已经构造的 Agent。

配置仓库中的“复制”调用 Primary 专用服务端 endpoint：后端按当前完整静态装配规则重新校验源记录，
生成新 UUID 并保存新名称。原 Primary、bindings 以及所有现有 UUID 引用不变；无效历史源、缺失源
或重复名称不会产生副本。
