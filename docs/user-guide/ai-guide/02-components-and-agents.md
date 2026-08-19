# 按需装配 Agent Filesystem

每个 Main Agent 可选择一份项目 Filesystem 或使用最小 Filesystem；Subagent 可继承、选择自己的项目 Filesystem 或回到最小 Filesystem。只有包含 Agent Node 时，才需要后续的
Model、Output Mode、Workflow Input Context（WIC）Middleware 和 Main Agent；不要为了满足 Graph contract 创建无调用方的 Agent。

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

Provider 和 Provider-specific 字段以模型页面及后端校验为准。不要照抄示例中的 model ID；先确认实例当前可用模型。

## Output Mode

Main Agent 必须引用完整 Output Mode。不要手写不完整的事件表；从 `GET /api/catalog` 复制
`editor_defaults.output_mode.default_value`，添加唯一 `name` 后提交到：

```http
POST /api/blocks/output-mode
```

若只需要最终 Assistant 文本，可以保留全部事件 key，但只启用 `assistant_text`：

```python
def output(event):
    return event["message"]
```

每个 `output_source` 必须恰好定义同步 `def output(event)` 并返回 `str`。完整八类事件及字段见
[输出模式](../../wizard-pages/output-mode-config.md)。

## Workflow Input Context Middleware

先请求：

```http
GET /api/python-package-templates/middleware
```

在 `catalog` 中按精确 `key == "内置示例-workflow-input-context"` 选择模板。使用该项返回的 `revision` 和 `files`
创建配置，不要从文档复制整份 WIC 源码：

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

提交到 `POST /api/blocks/custom-middleware`。服务端生成独占 package folder；客户端不能自行填写 UUID folder。

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
多个 Middleware 会改写 `messages` 时，必须有意识地确定顺序。

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
确有不同模型、提示、工具或权限时使用 `replace`/`disabled` override。Main Agent 还应引用 `subagent` 委派能力组件，
让 `task` 工具说明与路由提示符合当前业务。

Subagent 的 `name` 是模型可见路由名；`description` 应明确它何时被委派、负责什么、返回什么。不要创建层层嵌套的
Subagent 树，当前 contract 只支持 Main Agent 的一层直接 Subagent。

下一步：[创建 Workflow Graph](03-workflow-graph.md)。
