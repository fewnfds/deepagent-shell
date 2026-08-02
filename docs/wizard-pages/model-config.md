# 模型

模型 block 选择一个明确的 LangChain Provider integration，并保存连接、模型名和该 Provider 自己的
构造参数。Provider 描述实际 wire adapter；DeepAgent Shell 不按模型名称猜测 Provider，也不把一家
Provider 的参数改名后传给另一家。

当前版本随发行物固定内置以下 integration：

| Provider ID | LangChain 包 | 模型类 |
| --- | --- | --- |
| `openai` | `langchain-openai` | `ChatOpenAI` |
| `anthropic` | `langchain-anthropic` | `ChatAnthropic` |
| `google_vertexai` | `langchain-google-vertexai` | `ChatVertexAI` |
| `google_genai` | `langchain-google-genai` | `ChatGoogleGenerativeAI` |
| `deepseek` | `langchain-deepseek` | `ChatDeepSeek` |
| `xai` | `langchain-xai` | `ChatXAI` |

这些包由 DeepAgent Shell 的 `uv.lock` 随版本统一安装和升级。管理台没有安装、更新或任意包名入口。
本版不内置 OpenRouter integration。

## 编辑顺序与 Payload

Provider 位于模型编辑器顶部。输入框兼具下拉和模糊搜索，只接受本版本目录中的精确 Provider ID。
切换 Provider 会立即清空 `provider_settings`，再显示新 Provider 的原生参数组，避免已经填写的旧参数
跨 Provider 留存。

```json
{
  "name": "Reasoning model",
  "provider": "deepseek",
  "base_url": "https://api.deepseek.com",
  "credential": null,
  "model": "deepseek-reasoner",
  "provider_settings": {
    "max_tokens": 4096,
    "reasoning_effort": "high"
  },
  "tool_choice": null,
  "response_format": null,
  "model_settings": {}
}
```

`name`、`provider`、HTTP(S) `base_url`、`model`、`provider_settings`、`tool_choice`、
`response_format` 和 `model_settings` 都必须显式存在。缺键的旧记录保持无效；进入编辑器明确选择并
保存后才写成当前结构，读取和运行不会自动迁移。

## Provider 原生参数组

`provider_settings` 是所选 LangChain 模型类的原生构造参数对象。后端按 Provider 独立白名单验证，
然后不改名、不映射地展开给 `langchain.chat_models.init_chat_model()`。未知字段、错误 JSON 类型和
跨 Provider 参数都会拒绝保存。

当前编辑器提供的参数如下：

| Provider | 原生参数 |
| --- | --- |
| `openai` | `temperature`, `max_completion_tokens`, `top_p`, `stop_sequences`, `presence_penalty`, `frequency_penalty`, `seed`, `timeout`, `max_retries`, `stream_usage`, `streaming`, `reasoning_effort`, `service_tier`, `logprobs`, `top_logprobs` |
| `deepseek` | `temperature`, `max_tokens`, `top_p`, `stop_sequences`, `presence_penalty`, `frequency_penalty`, `seed`, `timeout`, `max_retries`, `stream_usage`, `streaming`, `reasoning_effort`, `service_tier`, `logprobs`, `top_logprobs` |
| `xai` | `temperature`, `max_tokens`, `top_p`, `stop_sequences`, `presence_penalty`, `frequency_penalty`, `seed`, `timeout`, `max_retries`, `stream_usage`, `streaming`, `reasoning_effort`, `service_tier`, `logprobs`, `top_logprobs` |
| `anthropic` | `temperature`, `max_tokens_to_sample`, `top_p`, `stop`, `timeout`, `max_retries`, `stream_usage`, `streaming`, `effort` |
| `google_genai` | `temperature`, `max_tokens`, `top_p`, `stop_sequences`, `presence_penalty`, `frequency_penalty`, `seed`, `request_timeout`, `retries`, `streaming`, `thinking_level`, `thinking_budget`, `include_thoughts` |
| `google_vertexai` | `temperature`, `max_tokens`, `top_p`, `stop_sequences`, `presence_penalty`, `frequency_penalty`, `seed`, `timeout`, `max_retries`, `streaming`, `logprobs`, `thinking_budget`, `include_thoughts` |

空控件表示不发送该可选参数。数值必须是有限 JSON number；token/retry/budget 等整数字段遵守页面与
后端显示的正数或非负数边界；`stop` / `stop_sequences` 使用字符串数组；布尔和枚举不做字符串到值的
服务端猜测。

`reasoning_effort`、Anthropic 的 `effort`、Google 的 `thinking_level` / `thinking_budget` 只控制
对应 Provider 接受的推理设置。省略参数表示采用 Provider 默认，并不保证关闭或开启可见 reasoning。
可见推理还取决于模型、wire 和所选 LangChain integration 是否产生标准 reasoning content block；
选错 Provider 不能靠填写 `reasoning_effort` 修复。

API 请求中的 `stream` 只控制 DeepAgent Shell 对客户端的传输形式，不等同于 model block 的 `streaming`。
Chat Completions 请求体中的临时生成参数覆盖尚未接通，当前以 model block 为准。

## 连接与凭据

- Base URL 不接受 userinfo、query 或 fragment，保存时移除末尾 `/`。
- 除 Vertex AI 外，模型构造显式传入当前 block 的 Key 或无凭据占位，不探测宿主模型 Key 环境变量。
- 更新现有模型时，`credential=null` 只有在 Provider 和 Base URL 都没有变化时才保留已存 secret；改变
  任一项而不输入新 Key 会清除旧 secret。普通响应只返回 `masked|missing`。
- `google_vertexai` 必须使用 Google Application Default Credentials；其 `credential` 必须为 `null`，
  页面禁用普通 Key 输入。ADC 的项目、位置和宿主认证由官方 integration/Google 环境负责。
- secret 明文保存在同一 SQLite 的独立表，当前不是加密 vault。

【获取模型】是原有的 OpenAI-compatible 目录辅助：它请求 `${base_url}/models`，只把返回中的模型
`id` 带回页面，并使用 Bearer Key。目录请求使用 DeepAgent Shell 内置的 curl HTTP transport，并携带明确
User-Agent，以兼容会按服务端 HTTP/TLS 客户端特征应用规则的上游网关。请求同时携带 Provider；只有
Provider 与 Base URL 都和已保存模型一致时才能复用其 secret。若原生服务不提供这种目录 wire，则
直接填写官方模型 ID。

`openai`、`deepseek` 和 `xai` 的 LangChain integration 同样使用这一进程级共享 transport，包括
Primary、Subagent、普通调用和流式调用；【获取模型】成功与真实 Agent 调用不会使用两套不同的 HTTP
实现。Anthropic 和 Google integration 继续使用各自官方客户端的传输。

## 模型请求设置

- `tool_choice` 留空为 `null`；也可填写 `auto`、`none`、`required`、`any`、具体工具名或所选
  LangChain ChatModel 支持的 JSON 值。非空值在每次 `ModelRequest` 中设置。
- `response_format` 留空为 `null`。非空值是传给 `create_deep_agent()` 的 JSON Schema 对象，顶层必须有
  非空 `title` 和 `description`。
- `model_settings` 必须是 JSON 对象，默认 `{}`。它作用于模型 bind 阶段，不能重复
  `tool_choice`、`response_format` 或 `tools`，也不能存放任何 secret。

服务端只验证当前可以静态确定的结构和冲突，不连接 Provider 探测某个模型是否支持具体值或组合。
Primary 与 Subagent 最终都必须有模型；Subagent 只能继承或替换，不能禁用。
