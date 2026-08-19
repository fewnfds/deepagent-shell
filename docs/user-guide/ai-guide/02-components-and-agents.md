# 按需装配 Agent Filesystem

每个 Main Agent 可选择一份项目 Filesystem 或使用最小 Filesystem；Subagent 可继承、选择自己的项目 Filesystem 或回到最小 Filesystem。只有包含 Agent Node 时，才需要后续的
Model、Output Mode、Workflow Input Context（WIC）Middleware 和 Main Agent；没有 Agent Node 的 Graph 不需要额外创建这些对象。

## Filesystem

不创建、不选择项目 Filesystem 时，Agent 自动使用空的请求级 StateBackend，并只暴露 `read_file`；这就是最小 Filesystem。只有需要 mapped route、初始文件或更多文件工具时才创建组件：

```http
POST /api/blocks/filesystem
Authorization: Bearer <management token>
Content-Type: application/json

{"name":"AI workflow filesystem"}
```

保存响应中的 `id`，并把它作为需要该配置的 Main Agent 或 Subagent 的 `filesystem` capability ref。

## Model

`credential` 是 management-only 的 write-only 输入。创建模型时在 HTTPS 或本机 loopback 连接中提交真实 Provider Key；
服务端会把它写入 `agent-shell.env` 的独立变量，并在模型 YAML 中只保存变量引用。响应不会回显明文。不要把 Key 写进
脚本、普通日志或后续 GET/PUT payload；编辑同一 Provider 与 Base URL 时传 `null` 会保留现有 Key。

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

Provider 和 Provider-specific 字段以模型页面及后端校验为准。示例中的 model ID 不是实例当前可用模型的事实来源。

## Output Mode

Main Agent 的必选引用包含完整 Output Mode。`GET /api/catalog` 的
`editor_defaults.output_mode.default_value` 提供完整事件表，添加唯一 `name` 后提交到：

```http
POST /api/blocks/output-mode
```

若只需要最终 Assistant 文本，可以保留全部事件 key，但只启用 `assistant_text`：

```python
def output(event):
    return event["message"]
```

每个 `output_source` 的固定入口是同步 `def output(event)`，返回类型为 `str`。完整八类事件及字段见
[输出模式](../../wizard-pages/output-mode-config.md)。

## Workflow Input Context Middleware

Middleware 模板目录来自：

```http
GET /api/python-package-templates/middleware
```

在 `catalog` 中按精确 `key == "内置示例-workflow-input-context"` 选择模板。使用该项返回的 `revision` 和 `files`
创建配置。catalog 返回的是当前源码和 revision，文档不复制整份 WIC 源码：

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

内置 WIC 给出三项建议起点：Main Agent 读取本次 Lifecycle 原始消息、Subagent 保留委派消息、Dispatcher worker 把自己的
私有 task 加入上下文。它们不是强制的业务策略。当前 Agent 可以在
`build_workflow_input_messages(state, runtime, request_messages, backend)` 中按职责选择原始请求、私有 State、父图快照、
Dispatcher task、Runtime Context、Store 或当前 Agent Filesystem 材料；不需要的默认步骤可以删除。详细边界见
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
多个 Middleware 改写 `messages` 时，列表顺序决定它们的组合方式。

## 可选 Subagent

Subagent 用于隔离复杂、长输出任务，不是画布 Node。先创建实体：

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

然后把 `{"subagent_id":"<UUID>"}` 加入 Main Agent 的 `subagents`。Subagent 默认继承 Main Agent 的可继承能力；只在
不同模型、提示、工具或权限可通过 `replace`/`disabled` override 表达。Main Agent 引用 `subagent` 委派能力组件后，
`task` 工具说明与路由提示来自当前业务配置。

Subagent 的 `name` 是模型可见路由名；清楚描述委派时机、职责和返回内容有助于模型路由。当前 contract 只支持
Main Agent 的一层直接 Subagent，不接受嵌套 Subagent 树。

下一步：[创建 Workflow Graph](03-workflow-graph.md)。
