# 创建组件

【组件】提供十一类可复用配置。保存组件后，还要在 Primary 或 Subagent 实体 settings 中引用才会参与运行。

| 组件 | 用途 | Primary 要求 | Subagent 策略 |
| --- | --- | --- | --- |
| 模型 | Provider、模型名、凭据和请求设置 | 必选 | 继承或替换 |
| 系统提示词 | 基础 system prompt | 可选 | 继承、替换或关闭 |
| 文件系统 | workspace、映射、临时文件和文件工具 | 可选 | 全请求共享，不单独覆写 |
| 文件系统权限 | 路径权限与文件工具、提示词覆写 | 可选 | 继承、替换或关闭 |
| 待办计划 | `write_todos` 与规划提示 | 可选 | 继承、替换或关闭 |
| 自定义工具 | 选择 `data/resources/custom_tools/` 中的工具 | 可选 | 继承、替换或关闭 |
| Skill | 选择 `data/resources/skills/` 中的 Skill | 可选 | 继承、替换或关闭 |
| 自定义 Middleware | 有序构造 LangChain Middleware | 可选 | 继承、替换或关闭 |
| 输出模式 | 把 v3 事件投影为响应文本 | 必选 | 只用于顶层 Primary |
| 异常重试 | Provider 或 ModelRetryMiddleware 重试 | 可选 | 继承、替换或关闭 |
| 委派能力 | 同步 Subagent 的提示与 `task` 说明 | 可选 | 继承、替换或关闭 |

组件编辑页从服务端 catalog 取得字段、默认值和资源发现结果。草稿校验与保存校验都以后端 contract
为准；记录使用 UUID 引用，重命名不会断开引用。

详细字段见[组件说明](../wizard-pages/README.md)。Agent 组合方式见
[装配 Primary 与 Subagent](configuration-workflow.md)。

自定义的启动前消息处理、LangChain Hook 和生命周期文件更新不属于组件，按 Agent 身份挂载自动化插件。见
[使用自动化插件](automation.md)。
