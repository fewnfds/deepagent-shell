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

模型不能关闭，文件系统固定共享，输出模式只用于 Primary。Subagent 页面还可选择 child 自己的有序实体
引用，形成多层同步委派。允许显式循环；同一个实体在一次请求中只构造一次，不会因递归层级重复构造。

不同 Agent 可以自由选择模型、提示词、工具和 Middleware；Provider prompt caching 是否命中取决于最终
请求前缀与 Provider 规则。

## 自动化装配

事件工作流和定时工作流不是组件。Primary 可分别选择零或一个工作流；Subagent 对两类工作流分别选择继承、
替换或关闭。同一个 Subagent 实体在一次请求中只有一套自动化运行态，即使被多条路径或递归调用；每次真实
委派仍会单独触发该 Subagent 的启动前 Hook。

Primary 和每个 Subagent 都有自己的客户端消息副本。事件脚本可以在构造 Primary 前或每次启动 Subagent 前
修改对应 `ctx.messages`，不会修改其他 Agent 的副本。详细脚本格式与边界见
[使用自动化工作流](automation.md)。

## 校验与生效

编辑页会把完整草稿提交给后端预校验，保存时后端再次校验。校验通过表示当前结构和静态引用可用，
不表示外部文件、依赖和 Provider 永远可用。

每个推理请求开始时，服务端在一次 SQLite 读事务中取得组件、Primary、Subagent 和凭据快照，再构造
Agent。保存、重命名或凭据更新不会修改正在执行的请求。
