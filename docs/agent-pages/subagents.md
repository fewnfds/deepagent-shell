# Subagent

Subagent 页面保存可复用的完整 Subagent 实体。实体只有被 Primary 或另一个 Subagent 引用时才参与运行：

```json
{
  "component_name": "web-researcher",
  "name": "researcher",
  "description": "Searches sources and returns evidence.",
  "settings": {
    "capability_overrides": [
      {"type": "system-prompt", "mode": "replace", "block_id": "UUID"},
      {"type": "custom-tool", "mode": "disabled", "block_id": ""}
    ],
    "subagents": [
      {"subagent_id": "UUID"}
    ],
    "automation": {
      "hooks": {
        "mode": "replace",
        "plugins": [
          {"plugin_id": "market-context", "enabled": true, "config": {}}
        ]
      },
      "periodic": {
        "mode": "disabled",
        "plugins": []
      }
    }
  }
}
```

- `component_name` 是实体库内唯一的配置名；
- `name` 是 Deep Agents 使用的路由名，`description` 告诉父 Agent 何时委派；
- settings 中未出现的能力继承父 Agent；
- `replace` 必须引用同类型组件；
- `disabled` 不带 `block_id`；
- 模型可继承或替换，不能关闭；
- 文件系统由整棵请求代理树共享，不参与覆写；
- 文件系统权限可以继承、替换或关闭；关闭表示使用无路径限制、无额外覆写的默认策略；
- 输出模式只属于顶层 Primary；
- 其余可覆写组件支持继承、替换或关闭。

`settings.automation.hooks` 与 `settings.automation.periodic` 分别使用 `inherit/replace/disabled`。replace 保存
该身份自己的同类 bindings；其他模式不保存插件配置。每个周期 binding 自己保存 interval，因此同一 Agent 的
周期插件可以使用不同间隔。自动化不是组件，不放入 `capability_overrides`，自定义 Tool 与自定义 Middleware
也继续使用各自 capability。

`settings.subagents[]` 是该 Subagent 自己可以调用的有序实体引用。父级引用不会自动复制给 child。同一个
实体在请求内无论从多少分支或显式循环到达，都只构造一个 Subagent graph；各次 `task` 调用仍分别执行。

同样地，一个实体在一次请求中只有一套 automation owner 和 Skill overlay；全部身份与 binding 共享本请求的
`ctx.vars` dict，每个周期 binding 至多一个 lifecycle loop。无插件时 Subagent 只接收 Deep Agents 原生 delegated
messages。Hook 插件的 prepare 显式建立基础多轮消息后，每次 `task` 调用才在其末尾追加本次 delegated messages。
需要每次 invocation 执行的逻辑使用插件原生 `before_agent` 等 Middleware Hook。

每次实际 `task` 调用都有新的 Shell invocation ID，并记录父 invocation 和 cause `tool_call_id`；同一 invocation 的
多轮 model/tool 循环保持同一身份。Hook binding 在 `runtime.context["agent_shell_invocation"]` 中取得只读身份和自己的
scratch 路径。因此同 profile 四次并行调用可以在各自 scratch 使用同名中间文件，而 prepare 和 Middleware factory
仍只按 owner/binding 执行一次。请求终态统一清理 scratch；插件写入 mapped 或其他外部路径时仍需自行协调并发。

同一次请求中的 Primary 与同步 Subagent 共享普通 workspace 和 mapped routes。每个 Agent 根据自己的
最终文件系统权限获得路径访问和文件工具，再根据最终 Skill 配置获得只读 `/skills/` 视图。请求结束后，
内存 workspace 不保留；mapped directory 的磁盘写入按本地文件系统持久化。
