# 装配 Primary 与 Subagent

## Primary

在【Agent / Primary Agent】填写名称并选择组件。模型和输出模式必选；其他类型各选零或一条。
保存成功且 API Server 运行时，Primary 名称会出现在 `/v1/models`。

需要委派时，先在 Subagent 页面创建实体，再在 Primary 中按顺序选择实体引用。Primary 只保存
`subagent_id`；路由名、用途说明和能力策略来自实体。一个父 Agent 不能重复引用同一实体，也不能同时引用
两个路由名相同的实体。

## Subagent 实体

在【Agent / Subagent】填写唯一组件配置名、模型可见的路由名、用途说明，并在 settings 中定义能力策略：

- 继承：沿用 Primary 的组件；
- 替换：选择同类型组件；
- 关闭：从 child 移除该可选能力。

模型不能关闭，文件系统固定共享，输出模式只用于 Primary。文件系统权限是独立能力，可以继承、替换或关闭，
因此 child 可以在同一个 workspace 上使用不同的路径权限和文件工具。Subagent 页面还可选择 child 自己的
有序实体引用，形成多层同步委派。允许显式循环；同一个实体在一次请求中只构造一次，不会因递归层级重复构造。

不同 Agent 可以自由选择模型、提示词、工具和 Middleware；Provider prompt caching 是否命中取决于最终
请求前缀与 Provider 规则。

## 自动化装配

自动化不是组件。Primary 分别保存有序 Hook bindings 和带独立间隔的周期 bindings；Subagent 对两类插件分别
选择继承 Primary、使用自己的插件或关闭。同一个 Subagent 实体在一次请求中只有一套 request-local ctx，每个
周期 binding 至多一个循环，即使被多条路径或递归调用；每次真实委派仍使用新的 LangGraph state。

无插件时，客户端 `messages[]` 不进入 Primary 或 Subagent 的活动消息：Primary 以空 messages 启动，Subagent 保持
Deep Agents 原生 delegated input。插件 `prepare` 可以在任何 Agent 图构造前从不可变
`ctx.request.messages` 读取原始事实，并显式写入对应身份的空 `ctx.messages`；只有这样产生的消息才会进入 Agent。
需要每次 invocation 运行的逻辑使用插件返回的 LangChain 原生 Middleware Hook。详细格式见
[使用自动化插件](automation.md)。

每个请求的 Primary 有独立 root invocation；每次真实 Subagent `task` 调用有新的 invocation ID、parent ID 和
cause tool-call ID。同 profile 构造一次不等于四次调用共享执行身份：四次并发委派仍有四套插件 scratch。该隔离
只覆盖平台提供的 `runtime/automation/` 临时目录，不拆分整棵 Agent 树共享的 Deep Agents filesystem。

## 校验与生效

编辑页会把完整草稿提交给后端预校验，保存时后端再次校验。校验通过表示当前结构和静态引用可用，
不表示外部文件、依赖和 Provider 永远可用。

每个推理请求开始时，服务端在一次 SQLite 读事务中取得组件、Primary、Subagent 和凭据快照，再构造
Agent。保存、重命名或凭据更新不会修改正在执行的请求。
