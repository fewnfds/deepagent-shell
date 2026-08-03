# Primary Agent

Primary Agent 是 `/v1/models` 中公开的 model。每条记录包含名称、组件引用和可选的有序 Subagent 实体引用：

```json
{
  "name": "writer",
  "capability_refs": [
    {"type": "model", "block_id": "UUID"},
    {"type": "output-mode", "block_id": "UUID"}
  ],
  "subagents": [
    {"subagent_id": "UUID"}
  ]
}
```

模型和输出模式必选；其他组件可选，每种类型最多引用一条记录。文件系统未选择时仍有请求级
StateBackend 和 `read_file`，但没有项目映射和写入工具。

每条引用只保存 `subagent_id`。路由 `name`、委派 `description` 和能力 settings 都来自被引用的 Subagent
实体，不在 Primary 中重复填写。同一父级不能重复引用同一实体，也不能引用两个具有相同路由 name 的实体。

父 Agent 只获得当前记录显式引用的 Subagent。启用委派能力组件且至少有一条有效引用时，
Deep Agents 提供 `task` 工具。当前支持同步 Subagent；允许显式自引用或循环引用，执行与终止由
Deep Agents/LangGraph 管理。

保存时服务端检查必选项、UUID、组件结构、实体引用、同父路由名冲突、可静态确定的工具名冲突和完整
Subagent 组合。

`automation` 可分别引用零或一个事件工作流、零或一个定时工作流。两者不属于 `capability_refs`；事件工作流
可在构造前修改 Primary 自己的消息副本，定时工作流只在本次请求生命周期运行。
磁盘资源、Python import 和 Provider 连接在真实请求中再次检查。配置变更只影响之后开始的请求。
