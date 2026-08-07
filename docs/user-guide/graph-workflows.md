# Graph-first 工作流（Graph Workflow）

当前版本把可执行流程建模为固定 Graph（图）。Graph Definition（图定义）保存节点、控制连线、可选数据连线和画布位置；保存后由后端编译成 LangGraph `StateGraph`，运行时不再修改拓扑。

## 入口名称与调用

入口使用 Entry Script（入口脚本）。它有一个用户自行填写的 `name`，这个名称就是 OpenAI-compatible API 的 `model` 值。名称只能包含大写字母、小写字母和横杠，例如 `Research-Graph`；平台不会自动补全，也不再添加 `agent-`、`workflow-` 或 `auto-` 前缀。

Entry Script 可选实现：

```python
def prepare(messages):
    return {
        "messages": messages,
        "shared": {"topic": "由脚本提取的主题"},
    }
```

`messages` 必须是标准 OpenAI chat messages（聊天消息数组）。脚本可以返回新的消息数组和共享对象；没有脚本时，Graph 直接使用原始消息。

## 节点、连线和 State

- Node（节点）执行一个确定步骤；当前内置 Value、Pass、Shared State Update、Router、Join、Main Agent Profile、Tool 和 Graph Call。
- Control Edge（控制边）表示“完成后激活谁”，可以按任意小写控制信号条件分支；Router 从 shared 路径读取值并发布该信号。
- Data Edge（数据边）只在端口之间传递小型 typed value（带类型值）。业务的大对象应写入 shared State（共享状态）。
- `shared` 是用户自行管理的 JSON object；`control` 是平台控制信息；`artifacts` 保存文件引用；`messages` 只在需要消息的节点中使用；`ports` 保存端口结果。
- 图必须显式填写 `entry_nodes`，因此回边可以形成 Loop（循环）；`recursion_limit` 直接传给 LangGraph 作为步骤保护上限。Join 使用 LangGraph 的多前驱 barrier（屏障）等待所有声明的分支，不是 Agent Shell 自己的调度器。

所有这些 State 会进入 LangGraph Checkpoint（检查点），因此取消后可以使用同一个 Run 的 `thread_id` 继续上一次已完成节点的状态。暂停是协作式的：当前节点完成后不再调度新节点，继续按钮会放行下一节点。

## 运行面板和事件

管理台的 Graph Run 面板会显示节点开始、完成、失败、共享 State 快照和最终状态，并提供 Pause（暂停）、Continue（继续）和 Stop（彻底终止）按钮。OpenAI 流式响应会在标准 chunk 之外发送 `agent_shell.event=graph_stream`，其中包含 `version=v3`、LangGraph `type`、命名空间和节点更新，客户端可按 Graph/Node/Agent 自行投影。

## Artifact Commit 演示

`commit` 是基于通用 Artifact（产物）服务的演示 Tool，不是 Graph 平台的唯一业务模型。它支持文本内容、二进制元数据、一次生命周期内去重和准备阶段提供的规则/转换脚本。需要按文件顺序整理结果时，可参考源码中的 `workflow/examples/commit_reconciler.py`；它只是普通用户组合，不会改变平台调度器。

## 当前边界

Graph 拓扑必须在保存/编译前确定。Python 准备脚本和节点代码可以读写 State、返回结果和选择已声明的控制边，但不能在运行中 `add_node` 或 `add_edge`。插件包可以在现有自动化插件目录中贡献 `workflow_nodes`，声明端口、配置 JSON Schema 和 async entrypoint；函数接收 `ctx`，返回 State update（可含 `outputs`/`status`）或官方 `Command`。示例见 `examples/automation-plugins/workflow-node-text-normalizer`。
