# 组件说明

| 顺序 | 页面 | 类型 |
| --- | --- | --- |
| 1 | [模型](model-config.md) | `model` |
| 2 | [系统提示词](system-prompt-config.md) | `system-prompt` |
| 3 | [文件系统](filesystem-config.md) | `filesystem` |
| 4 | [文件系统权限](filesystem-permissions-config.md) | `filesystem-permissions` |
| 5 | [待办计划](todo-list-config.md) | `todo-list` |
| 6 | [自定义工具](custom-tool-config.md) | `custom-tool` |
| 7 | [Skill](skill-config.md) | `skill` |
| 8 | [自定义 Middleware](custom-middleware-config.md) | `custom-middleware` |
| 9 | [输出模式](output-mode-config.md) | `output-mode` |
| 10 | [异常重试](exception-retry-config.md) | `exception-retry` |
| 11 | [委派能力](subagent-config.md) | `subagent` |
| 12 | [上下文摘要](summarization-config.md) | `summarization` |
| 13 | [Prompt 缓存](prompt-caching-config.md) | `prompt-caching` |
| Workflow | [准备](workflow-prepare-config.md) | `workflow-prepare` |
| Workflow | [事件输出](workflow-event-output-config.md) | `workflow-event-output` |
| Workflow | [条件路由](condition-router-config.md) | `condition-router` |
| Workflow | [任务分发](task-dispatcher-config.md) | `task-dispatcher` |

模型和输出模式是 Main Agent 必选组件；Filesystem 由 Workflow 必选，准备和事件输出由 Workflow 可选绑定；条件路由与任务分发由画布 Node 引用；
Main/Sub 只显示锁定继承 Filesystem。其余 Agent capability 按需引用。
组件使用 UUID 建立引用；名称用于显示。
编辑页提供草稿校验、新建、重置和保存，删除集中在配置仓库。
