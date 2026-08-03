# 装配 Primary 与 Subagent

## Primary

在【Agent / Primary Agent】填写名称并选择组件。模型和输出模式必选；其他类型各选零或一条。
保存成功且 API Server 运行时，Primary 名称会出现在 `/v1/models`。

需要委派时，选择委派能力组件并添加 bindings。每条 binding 填写唯一名称、用途说明和可选 Subagent
覆写。留空覆写表示 child 继承 Primary；没有必要为完整继承创建空覆写记录。

## Subagent 覆写

在【Agent / Subagent】定义能力策略：

- 继承：沿用 Primary 的组件；
- 替换：选择同类型组件；
- 关闭：从 child 移除该可选能力。

模型不能关闭，文件系统固定共享，输出模式只用于 Primary。Subagent 页面还可定义 child 自己的
bindings，形成多层同步委派。

Prompt Preset 在 Agent graph 启动前处理该 Agent 的输入。Subagent 选择 Preset 后，启动消息排在
delegated task 之前；不选择时 child 只接收 task 输入。不同 Agent 可以自由选择模型、提示词、工具和
Middleware；Provider prompt caching 是否命中取决于最终请求前缀与 Provider 规则。

## 校验与生效

编辑页会把完整草稿提交给后端预校验，保存时后端再次校验。校验通过表示当前结构和静态引用可用，
不表示外部文件、依赖和 Provider 永远可用。

每个推理请求开始时，服务端在一次 SQLite 读事务中取得组件、Primary、Subagent 和凭据快照，再构造
Agent。保存、重命名或凭据更新不会修改正在执行的请求。
