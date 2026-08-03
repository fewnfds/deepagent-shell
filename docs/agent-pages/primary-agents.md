# Primary Agent

Primary 保存一份加法式装配：

```json
{
  "name": "writer",
  "capability_refs": [
    {"type": "model", "block_id": "UUID"},
    {"type": "output-mode", "block_id": "UUID"}
  ],
  "subagents": []
}
```

## 能力引用

页面顺序为模型、系统提示词、文件系统、待办计划、自定义工具、Skill、自定义 Middleware、输出
模式、异常重试、提示词预设和 Subagent。每个 type 最多一项
`{type, block_id}`；未出现就是不装配。

模型和输出模式由 manifest 标为必需，页面没有“不装配”或清除选项，右侧草稿校验区
会逐项检查，管理 API 也拒绝缺少任一项的配置。filesystem 和其他项目能力可选；未选择 filesystem 时
Shell 仍保留 Deep Agents 必需的 StateBackend，并把 FilesystemMiddleware 限制为只暴露 `read_file`。
配置选择器和摘要只显示名称，
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
- output mode 与 Subagent block
= 一个由 `create_deep_agent()` 构造的同步 child graph
```

Subagent 不能选择其他 Primary，也不能覆写或关闭 Filesystem。同一次请求只装配一个 workspace：
Primary 与全部同步 Subagent 双向共享完整虚拟 `files` state、初始虚拟文件和 mapped routes。
每个 Agent 在共享普通 workspace 上叠加自己的只读 `/skills/` 视图，只能读取最终选中的 Skill；
未选路径返回 not found，且不会为此创建第二套普通 workspace。未选择项目 Filesystem 时，全链仍共享
Deep Agents 默认 StateBackend，但只暴露 `read_file`。同步 child 是 `create_deep_agent()` 构造的官方
`CompiledSubAgent`。Primary 的命名 bindings 不复制到 child；child 只使用目标 Subagent 覆写中显式保存的
bindings。全局关闭隐式 `general-purpose`，因此空列表没有 `task`；用户可通过普通自引用或循环引用明确
提供递归委派。当前不支持异步或 dynamic Subagent。

child 的最终 Prompt Preset 是冻结客户端消息与 Startup conversation 的唯一门禁。最终选择到 Preset 时，
child 的原生 `before_agent` Middleware 从请求 context 读取冻结客户端消息，应用该 Preset，追加 Startup
conversation，再把 Deep Agents 的 delegated task 放在末尾；最终没有 Preset 时不装配该 Middleware，
child 只接收 delegated task。该处理不携带 Primary 已产生的 AI/Tool 过程，不包裹 `CompiledSubAgent`，
并且每次委派只执行一次。

## Prompt Caching 边界

自由装配是产品基线，普通 binding 不保证与 Primary 共享 Provider 缓存。缓存对齐只是用户手工配置的
理论特殊情况：用户可以让 Primary 与 child 的最终 model、system prompt、冻结客户端消息处理结果、
按序 tool schema、response schema 和相关 model settings 实际一致，只让各自 Prompt Preset 末尾的
Startup conversation 区分身份。delegated task 会排在 child Startup conversation 之后；工具、结构化
输出和 Provider 内部序列化也可能参与缓存键，不能假定工具只是较后的提示词。

需要相同 `task` schema 时，应在 Primary 与 Subagent 覆写中保存名称、说明和顺序相同的显式 catalog；
不同 catalog 可以复用同一个模型可见 binding 名称，例如都叫 `worker`，名称只要求在各自 catalog 内
唯一。两侧继续由官方 `SubAgentMiddleware` 生成工具。最终请求任何一处不同都可能缩短可复用前缀。缓存是否
命中及其 token 门槛仍由具体 Provider/model 决定；需要核对时使用拦截测试比较最终 `ModelRequest`，
不要把配置相似等同于命中保证。

## 保存与运行

桌面宽度下，右侧草稿校验区占页面三分之一；窄屏下恢复为整行。校验区展示后端对当前完整草稿的结构与
静态装配报告；连续输入停止 1000ms 后刷新，离散选择可立即刷新，晚到的旧响应不会覆盖新草稿。错误行
包含具体 owner、字段 path 和原因。保存按钮不把最近报告当作授权，服务端保存与真实请求共享同一个静态装配
校验，不能由直接 API 调用绕过 required、引用、依赖、最终 Subagent 或静态工具名规则。最终公开
工具名在 Primary 与每个同步 Subagent 的 `create_deep_agent()` 前检查，重名会以稳定 422 拒绝，不再
静默覆盖。磁盘资源、Python 构造、依赖安装和 Provider 等运行现场问题仍在真实请求中检查。
保存失败会一次展示后端报告中的全部问题，并按当前中文/英文语言格式化；成功保存后，该 Primary 名称会在 API Server
通过静态门禁并处于 running 时成为 `/v1/models` 中的公开 model ID。
运行中的每个新请求都会从同一份请求级数据库快照解析该公开名称、Primary UUID 和全部装配；保存、
改名或删除只影响之后捕获快照的请求，不改写已经构造的 Agent。

配置仓库中的“复制”调用 Primary 专用服务端 endpoint：后端按当前完整静态装配规则重新校验源记录，
生成新 UUID 并保存新名称。原 Primary、bindings 以及所有现有 UUID 引用不变；无效历史源、缺失源
或重复名称不会产生副本。
