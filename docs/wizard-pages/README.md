# 组件页面

【组件】页面按以下顺序提供十二类配置：

1. [模型](model-config.md) — `model`
2. [系统提示词](system-prompt-config.md) — `system-prompt`
3. [文件系统](filesystem-config.md) — `filesystem`
4. [待办计划](todo-list-config.md) — `todo-list`
5. [自定义工具](custom-tool-config.md) — `custom-tool`
6. [Skill](skill-config.md) — `skill`
7. [自定义 Middleware](custom-middleware-config.md) — `custom-middleware`
8. [输出模式](output-mode-config.md) — `output-mode`
9. [异常重试](exception-retry-config.md) — `exception-retry`
10. [提示词预设](prompt-preset-config.md) — `prompt-preset`
11. [同步子代理（Synchronous Subagents）](subagent-config.md) — `subagent`
12. [Context Worker 委派](worker-delegation-config.md) — `worker-delegation`

Primary 与 Subagent 不在【组件】页面编辑，使用方式见
[Agent 页面](../agent-pages/README.md)。

模型和输出模式是每个 Primary 的两项必选组件；其余十类按需装配。只保存组件还不会
自动加入 Agent，必须在【Agent / Primary Agent】明确选择。

## 通用规则

- 服务端生成 UUID；名称只用于显示，前端草稿携带的显式 UUID 决定更新目标，引用也只认 UUID。
- 右侧校验区在连续输入停止 1000ms 后向后端提交完整草稿，显示有效、无效、校验中或不可用；
  前端只组装 payload 和渲染报告，不保存组件业务规则。保存按钮始终把当前 payload 交给
  服务端重新校验，失败时一次显示全部安全问题。
- 每页标题区提供新建、重置和保存，不提供上一步、下一步或删除；删除只在配置仓库。
- 没有被 Primary、有效 Subagent 或 Context Worker 选择的 block 不进入 runtime。
- 资源扫描成功不等于依赖、文件和 Python 构造在未来请求时仍然有效；真实请求会重新检查。
- 默认提示词直接显示在编辑框；与当前默认逐字相同保存 `null`，改动后保存完整覆写。
- 页面说明只描述当前已经存在的字段和使用方式。
