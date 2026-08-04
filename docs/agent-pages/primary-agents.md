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
  ],
  "automation": {
    "plugins": [
      {"plugin_id": "market-context", "enabled": true, "config": {}}
    ],
    "lifecycle_interval_seconds": null
  }
}
```

模型和输出模式必选；其他组件可选，每种类型最多引用一条记录。文件系统与文件系统权限集中在文件工作区
区域选择。文件系统未选择时仍有请求级 StateBackend，以及默认开启的 `ls`、`read_file`、`write_file`、
`edit_file`、`glob`、`grep`，但没有项目映射。

文件系统权限不绑定文件系统。未选择时路径默认可读写，并直接使用文件系统的提示词与工具配置；选择后按
有序规则限制内置文件工具，并可原子覆写文件系统提示词和单个文件工具。

每条引用只保存 `subagent_id`。路由 `name`、委派 `description` 和能力 settings 都来自被引用的 Subagent
实体，不在 Primary 中重复填写。同一父级不能重复引用同一实体，也不能引用两个具有相同路由 name 的实体。

父 Agent 只获得当前记录显式引用的 Subagent。启用委派能力组件且至少有一条有效引用时，
Deep Agents 提供 `task` 工具。当前支持同步 Subagent；允许显式自引用或循环引用，执行与终止由
Deep Agents/LangGraph 管理。

保存时服务端检查必选项、UUID、组件结构、实体引用、同父路由名冲突、可静态确定的工具名冲突和完整
Subagent 组合。

`automation` 不属于 `capability_refs`，直接保存有序 plugin bindings 和可选 lifecycle interval。插件可在所有
Agent 构造前 prepare Primary 自己的派生消息，可返回 LangChain 原生 Middleware，也可在本次请求生命周期运行
循环与 complete。原始客户端消息通过插件只读的 `ctx.request.messages` 保持不变。
磁盘资源、Python import 和 Provider 连接在真实请求中再次检查。配置变更只影响之后开始的请求。
