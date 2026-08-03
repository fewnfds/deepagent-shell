# API Server

首页显示 API Server 状态、接入地址和配置告警，并提供启动、停止、API Key 和单次请求初始消息条数
上限。管理台 navbar 在所有页面显示运行状态。

## 接口

```http
GET /v1/models
Authorization: Bearer <API Key>
```

返回当前可运行的 Primary 名称。

```http
POST /v1/chat/completions
Authorization: Bearer <API Key>
Content-Type: application/json

{
  "model": "writer",
  "messages": [{"role": "user", "content": "Write a summary."}],
  "stream": false
}
```

支持流式和非流式响应。当前输入接受 OpenAI-compatible 文本消息；客户端必须在每次请求中提交完整
`messages[]`。模型组件中的 `tool_choice`、`response_format` 和 `model_settings` 决定 Provider-bound
ModelRequest，请求体中的临时生成参数不会覆盖模型组件。

服务端接受可选 headers：

- `X-Request-ID`：格式有效时作为单次请求关联 ID，否则服务端生成；响应会返回最终值；
- `X-Agent-Session-ID`：把多次请求归入同一历史会话；省略时服务端创建并在响应中返回。

session ID 只用于观察记录，不会从数据库加载消息或拼接上下文。

## API Key 与状态

API Key 是 write-only 设置，用于 `/v1/*`；管理密码用于管理台和 `/api/*`。清除 API Key 后推理 API
不可用。API Server 启动会执行仓库静态校验；单个 Primary 的外部资源和 Provider 状态仍在请求时确认。

所有 API 调用都会形成有界历史记录。日志中心的精简预览不显示消息正文；management 鉴权的 RAW 下载
包含实际请求与响应内容，应按敏感数据处理。
