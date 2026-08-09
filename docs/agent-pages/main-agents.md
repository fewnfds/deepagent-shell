# Main Agent

Main Agent 是 `/v1/models` 中公开的 model。每条记录包含名称、组件引用和可选的有序 Subagent 实体引用：

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
    "hooks": [
      {"plugin_id": "market-context", "enabled": true, "config": {}}
    ],
    "periodic": [
      {
        "plugin_id": "market-refresh",
        "enabled": true,
        "config": {},
        "interval_seconds": 5
      }
    ]
  }
}
```

模型和输出模式必选；其他组件可选，每种类型最多引用一条记录。文件系统与文件系统权限集中在文件工作区
区域选择。文件系统未选择时仍有请求级 StateBackend，以及默认开启的 `ls`、`read_file`、`write_file`、
`edit_file`、`glob`、`grep`，但没有项目映射。

文件系统权限不绑定文件系统。未选择时路径默认可读写，并直接使用文件系统的提示词与工具配置；选择后按
有序规则限制内置文件工具，并可原子覆写文件系统提示词和单个文件工具。

每条引用只保存 `subagent_id`。路由 `name`、委派 `description` 和能力 settings 都来自被引用的 Subagent
实体，不在 Main Agent 中重复填写。同一父级不能重复引用同一实体，也不能引用两个具有相同路由 name 的实体。

父 Agent 只获得当前记录显式引用的 Subagent。启用委派能力组件且至少有一条有效引用时，Deep Agents 提供
`task` 工具。经典模式只支持同步的一层 `Main -> Subagent`；Subagent 不能再配置 child，多阶段编排留给 Workflow。

保存时服务端检查必选项、UUID、组件结构、实体引用、同父路由名冲突、可静态确定的工具名冲突和完整
Subagent 组合。

`automation` 不属于 `capability_refs`。Hook bindings 负责 prepare、LangChain 原生 Middleware 和 complete；
周期 bindings 各自保存 interval，在本次请求期间独立运行 lifecycle，并在终态 complete。两类列表、配置与
模块实例相互独立；需要 checkpoint 的共享业务数据使用公共 LangGraph state。原始客户端消息通过插件只读的
`ctx.request.messages` 保持不变；无插件时不会进入 Main Agent 活动消息。
磁盘资源、Python import 和 Provider 连接在真实请求中再次检查。配置变更只影响之后开始的请求。
