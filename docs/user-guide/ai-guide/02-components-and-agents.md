# 配置 Agent Filesystem 与 Agent

每个 Main Agent 可选择一份项目 Filesystem 或使用最小 Filesystem；Subagent 可继承、选择自己的项目 Filesystem 或回到最小 Filesystem。只有包含 Agent Node 时，才需要后续的
Model、Output Mode、Workflow Input Context（WIC）Middleware 和 Main Agent；没有 Agent Node 的 Graph 不需要额外创建这些对象。

## Filesystem

不创建、不选择项目 Filesystem 时，Agent 自动使用空的 request-scoped `StateBackend`，并只暴露 `read_file`；这就是最小 Filesystem。只有需要 mapped route、initial file 或更多 Filesystem Tool 时才创建 component：

```http
POST /api/blocks/filesystem
Authorization: Bearer <management token>
Content-Type: application/json

{"name":"AI workflow filesystem"}
```

保存响应中的 `id`，并把它作为 Main Agent 或 Subagent 的 `filesystem` capability ref。

## Model

`credential` 是 management-only 的 write-only input。创建 Model 时在 HTTPS 或本机 loopback 连接中提交真实 Provider Key；
服务端会把它写入 `agent-shell.env` 的独立 environment variable，并在 Model YAML 中只保存 variable reference。响应不会回显 plaintext。不要把 Key 写进
script、普通日志或后续 GET/PUT payload；编辑同一 Provider 与 Base URL 时传 `null` 会保留现有 Key。

```http
POST /api/blocks/model
Authorization: Bearer <management token>
Content-Type: application/json

{
  "name": "Primary model",
  "provider": "openai",
  "base_url": "https://api.openai.com/v1",
  "credential": "<write-only Provider API Key>",
  "model": "<current-model-id>",
  "provider_settings": {},
  "tool_choice": null,
  "response_format": null,
  "model_settings": {}
}
```

Provider 和 Provider-specific field 以 Model page 及 backend validation 为准。示例中的 model ID 不是当前实例可用 Model 的事实来源。

## Output Mode

Main Agent 的 required reference 包含完整 Output Mode。`GET /api/catalog` 的
`editor_defaults.output_mode.default_value` 提供完整 event catalog，添加唯一 `name` 后提交到：

```http
POST /api/blocks/output-mode
```

若只需要最终 Assistant text，可以保留全部 event key，但只启用 `assistant_text`：

```python
def output(event):
    return event["message"]
```

每个 `output_source` 的固定 entry 是同步 `def output(event)`，return type 为 `str`。完整八类 event 及 field 见
[Output Mode](../../wizard-pages/output-mode-config.md)。

## Workflow Input Context（WIC）Custom Middleware

Middleware template catalog 来自：

```http
GET /api/python-package-templates/middleware
```

在 `catalog` 中按精确 `key == "内置示例-workflow-input-context"` 选择 template。使用该项返回的 `revision` 和 `files`
创建 Custom Middleware。catalog 返回的是当前 source 和 revision，文档不复制整份 WIC source：

```json
{
  "name": "Default workflow input context",
  "python_package": {
    "folder": "",
    "editable_files": ["main.py", "requirements.txt"]
  },
  "python_package_files": {
    "template_key": "内置示例-workflow-input-context",
    "revision": "<catalog revision>",
    "files": [
      {"path": "main.py", "content": "<main.py content returned by catalog>"},
      {"path": "requirements.txt", "content": "<requirements content returned by catalog>"}
    ]
  }
}
```

提交到 `POST /api/blocks/custom-middleware`。独占 package folder 由服务端生成，客户端 payload 中的 folder 初始为空。

内置 WIC 给出三项建议起点：Main Agent 读取本次 Lifecycle 的 request `messages[]`、Subagent 保留 delegated messages、Task Dispatcher worker 把自己的
private task 加入 Agent context。它们不是强制的业务策略。当前 Agent 可以在
`build_workflow_input_messages(state, runtime, request_messages, backend)` 中按职责选择 request messages、private State、parent Graph snapshot、
Task Dispatcher task、Runtime Context、Store 或当前 Agent Filesystem 材料；不需要的默认步骤可以删除。详细边界见
[Workflow Input Context](../workflow-input-context.md)。

## Main Agent

最小 Main Agent 引用 Model、Output Mode 和 WIC：

```http
POST /api/main-agents
Authorization: Bearer <management token>
Content-Type: application/json

{
  "name": "Primary worker",
  "capability_refs": [
    {"type": "model", "block_id": "<model UUID>"},
    {"type": "output-mode", "block_id": "<output-mode UUID>"}
  ],
  "middleware_refs": [
    {"middleware_id": "<WIC UUID>"}
  ],
  "subagents": []
}
```

`middleware_refs` 有顺序：LangChain 的 `before_*` hook 正序执行，`after_*` 逆序执行，`wrap_*` 按列表嵌套。
多个 Middleware 改写 `messages` 时，list order 决定组合方式。

## 可选 Subagent

Subagent 用于隔离复杂或长输出 task，不是 canvas Node。先创建 Subagent entity：

```http
POST /api/subagents

{
  "component_name": "Research specialist",
  "name": "researcher",
  "description": "Researches the delegated question and returns concise evidence with sources.",
  "settings": {
    "capability_overrides": [],
    "middleware_refs": []
  }
}
```

然后把 `{"subagent_id":"<UUID>"}` 加入 Main Agent 的 `subagents`。Subagent 默认继承 Main Agent 的 inheritable capability；不同的
Model、system prompt、Tool 或 Filesystem Permissions 通过 `replace`/`disabled` override 表达。Main Agent 引用 `subagent` delegation capability component 后，
`task` Tool description 与 routing prompt 来自当前业务配置。

Subagent 的 `name` 是 Model-visible routing name；清楚描述 delegation timing、职责和 return content 有助于 Model routing。当前 contract 只支持
Main Agent 的一层直接 Subagent，不接受嵌套 Subagent 树。

下一步：[创建 Workflow Graph](03-workflow-graph.md)。
