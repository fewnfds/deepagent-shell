# Primary Agent

Primary Agent 是 `/v1/models` 中公开的 model。每条记录包含名称、组件引用和可选 Subagent bindings：

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

模型和输出模式必选；其他组件可选，每种类型最多引用一条记录。文件系统未选择时仍有请求级
StateBackend 和 `read_file`，但没有项目映射和写入工具。

每条 Subagent binding 包含：

- `name`：当前 Agent 内唯一的工具目录名，匹配 `[A-Za-z_][A-Za-z0-9_-]*`；
- `description`：告诉父 Agent 何时委派；
- `subagent_override_id`：可选覆写 UUID，留空表示继承 Primary 的能力。

父 Agent 只获得当前记录显式列出的 bindings。启用委派能力组件且至少有一条完整 binding 时，
Deep Agents 提供 `task` 工具。当前支持同步 Subagent；允许显式自引用或循环引用，执行与终止由
Deep Agents/LangGraph 管理。

保存时服务端检查必选项、UUID、组件结构、binding、可静态确定的工具名冲突和完整 Subagent 组合。
磁盘资源、Python import 和 Provider 连接在真实请求中再次检查。配置变更只影响之后开始的请求。
