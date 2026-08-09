# 装配 Workflow、Main Agent 与 Subagent

## Workflow

【Workflow】是 OpenAI-compatible `model` 的唯一来源。首版 Workflow 保存名称、说明、启用状态和一个 Main Agent
引用。请求时服务端把它编译成真实 LangGraph 根图：

```text
START -> agent -> END
```

只有启用的 Workflow 出现在 `/v1/models`。Workflow 名称与 Main Agent 名称相互独立；修改 Main Agent 名称不会
改变公开 model ID。

## Main Agent 与直接 Subagent

在【Agent / Main Agent】选择模型和输出模式等 capability。需要委派时，先创建 Subagent 实体，再由 Main Agent
按顺序保存 `subagent_id` 引用并选择委派 capability。

Subagent settings 只定义身份、说明和 capability 覆写。它没有 child 引用字段。当前固定为一层同步
`Main -> Subagent`，运行时使用 Deep Agents 官方 dictionary-based SubAgent；多阶段、并行、条件和 join 属于后续
Workflow 图编辑器。

## 自定义 Middleware

Custom Middleware 组件保存有序 Middleware 包引用。Main Agent 选择组件后，直接 Subagent 按 capability 的
继承/替换/关闭规则得到自己的最终列表。Shell 只负责包加载并把官方 `AgentMiddleware` 实例交给
`create_deep_agent()`，不存在 prepare、周期循环或结束 Hook。

客户端 `messages[]` 是外围不可变请求事实，不会自动成为 Main Agent 活动消息。需要消息策略时，由 Middleware
在 `before_agent`/`abefore_agent` 中读取 `ctx.request.messages` 并返回 state update。Subagent 默认保留 Deep Agents
delegated messages。格式见[自定义 Middleware 包](middleware-packages.md)。

## 校验与生效

编辑页提交完整草稿给后端预校验，保存时再次校验。每个推理请求从一次 SQLite 快照解析 Workflow、Main Agent、
直接 Subagent、组件和 Provider secret；运行中的请求不受后续配置修改影响。
