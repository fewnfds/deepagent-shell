# 验证、启用和真实调用

配置完成后按有限清单验收：

1. `GET /api/validation/repository`，确认本次创建的组件和 Agent 没有 error。
2. `POST /api/workflows/{id}/validate` 提交候选 Graph，修正返回的全部 error。
3. `PUT /api/workflows/{id}/graph` 正式保存；返回成功后再用 GET 核对 UUID、handle、Command branch key、Dispatcher task key
   和布局节点键。
4. 通过 `PUT /api/api-server` 设置独立 API Key；不要复用 management token：

```json
{
  "api_key": {"operation": "replace", "value": "<new printable ASCII key>"},
  "max_initial_messages": 1000
}
```

5. `POST /api/api-server/start`。
6. 使用 API Key 调用 `GET /v1/models`，确认 Workflow 名称出现。
7. 使用同一名称调用一次非流式 `/v1/chat/completions`，确认 Workflow 真实运行并返回预期结果。

```http
POST /v1/chat/completions
Authorization: Bearer <API Key>
Content-Type: application/json

{
  "model": "ai-workflow",
  "messages": [
    {"role": "system", "content": "Follow the requested output format."},
    {"role": "user", "content": "Return exactly: workflow-ready"}
  ],
  "stream": false
}
```

不要仅以“配置保存成功”作为验收。Graph 引用、Python 扩展、Provider 和输出脚本只能由真实运行全部闭合。没有 Agent Node
的 Workflow 也必须真实调用；不要假设它一定产生 Assistant 文本。

## 详细文档

- 所有组件及必选/继承策略：[创建组件](../capabilities.md)
- Main Agent、Subagent、Workflow 语义：[Workflow、Main Agent 与 Subagent](../configuration-workflow.md)
- WIC 与前序 invocation 读取：[Workflow Input Context](../workflow-input-context.md)
- Python package、模板、依赖和加载：[文件化 Python 扩展](../middleware-packages.md)
- Command 节点完整 contract：[Command 节点](../../wizard-pages/command-config.md)
- Task Dispatcher 完整 contract：[任务分发](../../wizard-pages/task-dispatcher-config.md)
- Output Mode 稳定事件字段：[输出模式](../../wizard-pages/output-mode-config.md)
- Workflow Event Output 字段：[事件输出](../../wizard-pages/workflow-event-output-config.md)
- OpenAI-compatible 运行入口：[API Server](../api-server.md)
- 后台 Run、Lifecycle 清场与多 Run 语义：[Workflow、Main Agent 与 Subagent](../configuration-workflow.md)
- Debug thread、checkpoint 与日志边界：[日志中心与 Workflow 观测](../runtime-observability.md)
- secret 与远程访问边界：[安全与部署](../../security-and-deployment.md)

Agent Shell 使用 Deep Agents 官方装配和 LangGraph Graph API。设计 Agent 时遵循官方上下文工程原则：始终相关的约定放在
精简提示中，任务特定材料由 WIC/Skill 按需加载；长且独立的工作委派给描述清晰的 Subagent；大结果放入共享
Filesystem 后按需读取。参考 [Deep Agents context engineering](https://docs.langchain.com/oss/python/deepagents/context-engineering)、
[Subagents](https://docs.langchain.com/oss/python/deepagents/subagents) 和
[Custom middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom)。
