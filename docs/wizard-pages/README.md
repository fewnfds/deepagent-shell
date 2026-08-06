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
| 12 | [其他配置](other-config.md) | `other` |

模型和输出模式是 Primary 必选组件。其余组件按需引用。组件使用 UUID 建立引用；名称用于显示。
编辑页提供草稿校验、新建、重置和保存，删除集中在配置仓库。
