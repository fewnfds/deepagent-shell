# Validation、enabled 与真实 invocation

配置完成后按有限 checklist 验收：

1. `GET /api/validation/repository`，确认本次创建的 component 和 Agent 没有 error。
2. `POST /api/workflows/{id}/validate` 提交 candidate Graph，修正返回的全部 error。
3. `PUT /api/workflows/{id}/graph` 保存并设置 `enabled=true`；返回成功后再用 GET 核对 UUID、handle、Command branch key、Task Dispatcher task key
   和 layout Node key。
4. 通过 `PUT /api/api-server` 设置独立 API Key；management token 与 inference API Key 属于两个 credential domain：

```json
{
  "api_key": {"operation": "replace", "value": "<new printable ASCII key>"},
  "max_initial_messages": 1000
}
```

5. `POST /api/api-server/start`。
6. 使用 API Key 调用 `GET /v1/models`，确认 Workflow name 出现。
7. 使用同一 name 发起一次 non-streaming `/v1/chat/completions` invocation，确认 Workflow 执行并返回 expected result。

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

配置保存成功只证明 persistence 完成；真实 invocation 才会闭合 Graph reference、Python extension、Provider 和 output script。没有 Agent Node
的 Workflow 同样可以 invoke，但不保证产生 Assistant text。

## 详细文档

- 所有 Agent component 及 required/inheritance policy：[Agent component](../capabilities.md)
- Main Agent、Subagent、Workflow 语义：[Workflow、Main Agent 与 Subagent](../configuration-workflow.md)
- WIC 与前序 invocation 读取：[Workflow Input Context](../workflow-input-context.md)
- Python package、template、dependency 和 loading：[File-based Python extension](../middleware-packages.md)
- Command Node 完整 contract：[Command Node](../../wizard-pages/command-config.md)
- Task Dispatcher 完整 contract：[Task Dispatcher](../../wizard-pages/task-dispatcher-config.md)
- Agent Event Output 稳定 event field：[Agent Event Output](../../wizard-pages/agent-event-output-config.md)
- Workflow Event Output field：[Workflow Event Output](../../wizard-pages/workflow-event-output-config.md)
- OpenAI-compatible Run entry point：[API Server](../api-server.md)
- background Run、Lifecycle cleanup 与 multi-Run semantics：[Workflow、Main Agent 与 Subagent](../configuration-workflow.md)
- Debug thread、checkpoint 与 log boundary：[Runtime observability](../runtime-observability.md)
- secret 与远程访问边界：[安全与部署](../../security-and-deployment.md)

Agent Shell 使用 Deep Agents 官方 assembly 和 LangGraph Graph API。官方 context engineering 把始终相关的约定放在
concise prompt 中，由 WIC/Skill 按需加载 task-specific material，把长且独立的工作交给描述清晰的 Subagent，并把 large result 放入 shared
Filesystem 后按需读取。参考 [Deep Agents context engineering](https://docs.langchain.com/oss/python/deepagents/context-engineering)、
[Subagents](https://docs.langchain.com/oss/python/deepagents/subagents) 和
[Custom middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom)。
