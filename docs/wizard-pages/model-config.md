# 模型

模型组件保存一个 LangChain Provider integration、连接信息和请求设置。

| Provider ID | LangChain 类 | 凭据 |
| --- | --- | --- |
| `openai` | `ChatOpenAI` | API Key |
| `anthropic` | `ChatAnthropic` | API Key |
| `google_genai` | `ChatGoogleGenerativeAI` | API Key |
| `google_vertexai` | `ChatVertexAI` | Application Default Credentials |
| `deepseek` | `ChatDeepSeek` | API Key |
| `xai` | `ChatXAI` | API Key |

```json
{
  "name": "Reasoning model",
  "provider": "deepseek",
  "base_url": "https://api.deepseek.com",
  "credential": null,
  "model": "deepseek-reasoner",
  "provider_settings": {"max_tokens": 4096},
  "tool_choice": null,
  "response_format": null,
  "model_settings": {}
}
```

## 字段

- `base_url` 必须是无 userinfo、query、fragment 的 HTTP(S) URL；
- `credential` 是 write-only。编辑时留空会在 Provider 与 Base URL 未变时保留已有值；改变连接而未填
  新 Key 会清除已有值；Vertex AI 固定使用 ADC；
- `provider_settings` 只接受当前 Provider 白名单中的原生参数，切换 Provider 会清空该对象；
- `tool_choice` 可以是字符串、布尔值、JSON 对象或 `null`；
- `response_format` 为 JSON Schema 对象或 `null`，非空时要求 `title` 和 `description`；
- `model_settings` 为 bind 阶段 JSON 对象，不能包含 `tools`、`tool_choice` 或 `response_format`。

当前 Provider 参数：

- OpenAI：`temperature`, `max_completion_tokens`, `top_p`, `stop_sequences`, `presence_penalty`,
  `frequency_penalty`, `seed`, `timeout`, `max_retries`, `stream_usage`, `streaming`, `reasoning_effort`,
  `service_tier`, `logprobs`, `top_logprobs`；
- DeepSeek/xAI：同上，token 字段为 `max_tokens`；
- Anthropic：`temperature`, `max_tokens_to_sample`, `top_p`, `stop`, `timeout`, `max_retries`,
  `stream_usage`, `streaming`, `effort`；
- Google GenAI：`temperature`, `max_tokens`, `top_p`, `stop_sequences`, `presence_penalty`,
  `frequency_penalty`, `seed`, `request_timeout`, `retries`, `streaming`, `thinking_level`,
  `thinking_budget`, `include_thoughts`；
- Google Vertex AI：`temperature`, `max_tokens`, `top_p`, `stop_sequences`, `presence_penalty`,
  `frequency_penalty`, `seed`, `timeout`, `max_retries`, `streaming`, `logprobs`, `thinking_budget`,
  `include_thoughts`。

【获取模型】调用 `${base_url}/models` 读取 OpenAI-compatible 模型目录。真实 Agent 是否支持某个参数组合
由目标 Provider 和模型决定，静态保存校验不会发起探测。
