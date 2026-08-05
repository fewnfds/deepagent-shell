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

支持流式和非流式响应。客户端必须在每次请求中提交完整 `messages[]`；core 只保存和校验这份请求事实，不会在
没有 automation prepare 的情况下自动交给 Primary 或 Subagent。模型组件中的 `tool_choice`、`response_format` 和
`model_settings` 决定 Provider-bound ModelRequest，请求体中的临时生成参数不会覆盖模型组件。

`content` 可以是字符串，或由下列受控 content parts 组成的数组：

- OpenAI Chat 形状：`text`、`image_url`、`input_audio`、`file`；
- Agent Shell 标准扩展：`image`、`audio`、`video`、`file`，用于直接表达 LangChain 标准 block。

入口会把两种形状统一规范化为 LangChain `text/image/audio/video/file` blocks，同时保持消息角色、楼层和块顺序。
system 消息第一阶段只接受字符串或 text blocks，不接受媒体。标准媒体 block 必须且只能提供 `url`、`base64`、
`file_id` 一种来源；base64 必须同时提供与 block 类型相符的 `mime_type`。URL 只接受不含凭据的绝对
`http`/`https` 地址；Shell 不下载它。`file_id` 原样交给所选 Provider，因此只能引用该 Provider 可识别的文件。

固定输入边界为：请求 JSON 最多 64 MiB、全部消息最多 4096 个 content blocks、单个 base64 解码后最多 24 MiB、
一次请求全部 base64 解码后最多 48 MiB。更大的媒体应使用 Provider 支持的 URL 或 `file_id`。未知 block、畸形
data URI/base64、错误 MIME family 和多来源 block 在 Provider 调用前返回 422。LangChain 标准块不等于所有
Provider 都支持相同 modality、来源或 assistant 历史；合法的 Provider adapter 降级或拒绝保持其原生语义。

## 多模态输出

最终 Primary 响应中的 `image/audio/video/file` block 不会作为 Chat content-parts 或 Web 链接返回。Shell 只在能从
base64 或 data URI 取得有效字节时，将媒体保存到实例私有的
`data/media/outputs/<年月>/<request-id>/`，并在该 block 原位置向标准字符串响应插入：

```text
AI发送来了【图片】，已保存到【data/media/outputs/<年月>/<request-id>】。
```

非流式响应仍使用 `choices[0].message.content` 字符串；流式响应使用普通 `delta.content`。每个媒体 block 最多生成
一次通知，单个输出媒体最多 64 MiB。远程 URL、Provider `file_id`、无效或超限内容不会由 Shell 下载，并只返回
`AI发送来了【图片】，但返回内容无法保存。`，不会错误声称已经落盘。

API history 和 Agent session 另外保存去除正文后的结构化 blocks 与资产引用，用于管理查看和引用清理；其中只有
以 `data/` 为根的逻辑相对路径，不含 base64、媒体 URL 或宿主绝对路径。媒体目录没有 HTTP endpoint，也不属于文件
管理器 scope。只要 API history 或 session 仍引用资产，重启后文件继续保留；全部引用随 retention 或人工删除消失后，
对应文件会清理。

这是 Chat Completions 的有意降级，不是无损多模态往返。客户端下一轮重放的通知只是普通 assistant 文本，Shell
不会把其中的路径恢复为媒体 block。Subagent、reasoning、tool 和其他内部模型媒体不会因此进入 Primary 公开响应。

服务端接受可选 headers：

- `X-Request-ID`：格式有效时作为单次请求关联 ID，否则服务端生成；响应会返回最终值；
- `X-Agent-Session-ID`：把多次请求归入同一历史会话；省略时服务端创建并在响应中返回。

session ID 只用于观察记录，不会从数据库加载消息或拼接上下文。

请求中以 assistant 开始或结束的历史仍按原角色交给所选 Provider；尾部 assistant 在协议语义上属于 prefill，
部分 Provider/模型会拒绝。Agent Shell 不为此合成 user 消息或承诺全部 Provider 接受任意角色排列。
需要人工 assistant 引导时，更便携的做法是补成完整 user/assistant 示例，并以新的 user 消息触发生成。

## API Key 与状态

API Key 是 write-only 设置，用于 `/v1/*`；管理密码用于管理台和 `/api/*`。清除 API Key 后推理 API
不可用。API Server 启动会执行仓库静态校验；单个 Primary 的外部资源和 Provider 状态仍在请求时确认。

所有 API 调用都会形成有界历史记录。日志中心的精简预览不显示消息正文；management 鉴权的 RAW 下载
包含实际请求与响应内容，应按敏感数据处理。
