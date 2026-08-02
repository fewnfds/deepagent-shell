# 日志中心与历史会话

【系统 / 日志中心】按时间合并 API 调用、拦截记录、系统日志和 Agent 运行日志。日志列表支持来源、
级别和全文查询；request ID 可以直接作为查询条件关联同一次请求的不同来源。筛选控件中的修改只有在
提交搜索后才成为已应用条件；重置会恢复页面首次打开时的默认条件并回到第一页。

日志时间窗口默认是浏览器本地今天 `00:00:00` 到页面首次打开时的“现在”。结束时间会作为已应用条件
保持不变，因此普通翻页、SSE 和重渲染不会把查询偷偷推进到最新日志；用户也可以直接编辑开始、结束
时间。管理 SSE 收到相关变化后只显示【载入新事件】。点击该按钮或页面【刷新】时，才把结束时间推进到
点击时的“现在”，保留开始时间、来源、级别和全文查询，并回到第一页。

固定时间窗口内使用普通页码：默认每页 50 条，也可切换为 25 或 100 条，并支持首页、上一页、下一页、
末页和直接跳转。保存上限、轮转或删除可能使当前页超过新的末页，此时页面显示合法空结果，不自动发起
第二次请求校正页码。

每个条目在统一表格中显示时间、来源、级别和摘要；点击日志行可展开或收起详情。API 调用首次展开时按需
读取精简 RAW JSON：保留
request ID、模型、Agent、状态、时间和 HTTP 信息。请求体按白名单显示模型、流式开关和有限生成参数，
多轮 `messages` 数组整体移除，只保留 `messages_omitted` 数量；响应体按白名单显示 completion 标识、
finish reason、usage 和终止状态，不显示 `choices.message`、流式 `delta` 或任何响应正文。未知字段默认不
进入预览。完整正文不会为了预览重新进入列表响应。其他来源的短日志
继续在该行下方显示完整 JSON。超过 4 KiB 的完整内容不进入列表，只保留摘要，并通过该行的下载操作取得
management 鉴权的 JSON 文件。下载时记录若已被保存上限裁剪或主动删除，页面会提示失败；Agent 运行
日志重启后仍从结构化存储读取。

API 调用条目提供下载图标加【RAW】和【DEBUG】两个紧凑操作。RAW 保持数据库中记录的完整
wire；调试版只在下载时把 SSE `chat.completion.chunk` 合并为一段可读 content，并保留分块数、结束
原因、usage、错误和 DeepAgent Shell 终止信息，同时把可解析的请求与非流式响应 JSON 还原为对象。调试版
还会按 request ID 附带当前保留范围内的脱敏 Agent 运行诊断，包括稳定错误代码、安全调用位置和异常链。
RAW 不混入这些诊断；调试版不改写原始记录，也不承担 API wire 正文脱敏，分享文件前仍应按安全边界
检查其中的用户内容。

request ID 是 DeepAgent Shell 的请求关联 ID，不是 LangChain ID。客户端若提供唯一且格式有效的
`X-Request-ID`，服务端沿用该值；否则生成 `req_<uuid>`。它通过响应头返回，并保存在下载 JSON 的
`entry.request_id`，不会写进交给模型的 OpenAI 请求正文。需要关联同一请求的 API 调用、Agent 运行、
系统和拦截日志时，可从精简预览或下载 JSON 复制该值，并在全文查询框中搜索。

【系统 / 系统配置】保存拦截测试开关；该设置持久化，服务重启后仍按用户选择决定是否短路 Provider。
日志中心【保存策略】顶部保存详细诊断开关，默认关闭且同样跨重启生效。详细诊断只额外记录 lifecycle、
tool 和 Subagent 元数据，不保存逐 token 输出，也不控制核心错误详情；拦截测试开启时日志中心持续显示
警告。

每条请求完成运行日志记录 `reasoning_tokens=<数字>`；该数值来自 LangChain usage，并累计请求中的
全部模型调用。Provider 未上报时明确记录 `reasoning_tokens=unreported`，与明确上报的 `0` 区分。
该日志只保存数字，不复制 reasoning 正文。

日志中心的【保存策略】分别管理容量：

- API 调用、拦截记录和 Agent 运行日志默认各保留最近 20 条，可设置 1–10,000；降低上限会先确认范围，
  确认后立即裁剪超额旧项；三类结构化记录与上限都持久化，服务重启后继续展示保留范围内的记录；
- 系统日志只保留一个当前文件，不创建备份；默认最大 5 MiB，可设置 1–1024 MiB。降低上限且当前文件
  已超过新值时会清空当前日志，页面会在保存前确认；
- Agent 运行日志只把结构化 SQLite 记录作为持久数据；终端仍输出同一安全诊断供实时观察，但程序不再
  创建独立的 `runtime.log` 文件。

日志列表的【批量删除】会把已应用的开始时间、结束时间、来源、级别和全文查询条件原样交给后端，并删除
四类来源中全部匹配的日志，包括尚未加载到当前页面的结果；时间窗口外的日志始终保留。操作必须先通过
危险确认。删除 Agent 运行日志会删除唯一的结构化持久记录。

系统日志包含服务生命周期、配置/凭据操作、认证失败和管理 API 错误的脱敏 metadata。Agent 运行
日志包含请求开始、结束、安全错误、稳定代码、异常类型和相对调用位置。它们不包含用户消息、提示词、
请求体、工具参数/结果、Provider 原始响应、凭据、locals、宿主绝对路径或原始 traceback。

统一读取接口为 `GET /api/event-feed`，读取时必须提供带时区的 `started_at`、`ended_at`，并使用
`page`、`page_size` 进行页码分页；完整条目下载接口为
`GET /api/event-feed/{source}/{id}/download`，均需要 management scope。
API 调用的调试版使用同一路径并增加 `view=debug`；省略参数或使用 `view=raw` 时下载原始版。
系统日志大小设置使用 `GET/PUT /api/event-feed/system/settings`，PUT 只接受整数 `max_size_mib`。

## 历史会话

【系统 / 历史会话】使用紧凑列表展示时间、Agent、模型请求数和查看、下载、删除操作。列表不重复显示
“已完成”状态；失败或客户端断开仍会在详情中提示。点击列表【查看】进入以模型请求编号的 AdminLTE
Timeline；完整会话 JSON 只由列表中的【下载】生成文件，不在详情中重复显示。

会话列表支持关键字、Agent 包含匹配和最终状态筛选；文本匹配使用 NFKC 归一化并忽略大小写。服务端
返回权威总数，因此列表支持首页、上一页、下一页、末页、直接页码跳转和每页 20/50/100 条。筛选草稿
只有提交后才影响读取和批量动作；重置会恢复全部会话并回到第一页。

每次有效的 Primary `/v1/chat/completions` 请求正常记录后，在 `agent_session_runs` 中占一行。
第一轮没有 `X-Agent-Session-ID` 时，响应头会返回服务端生成的 ID；后续请求带回该值即可组成
多轮会话。request ID 仍只标识单次请求，也允许客户端重试时重复使用。

会话只在一次请求结束时写入完整的 `completed`、`failed` 或 `client_disconnected` 记录，不会在执行
前先保存一条 `running` 中间记录。因此正在执行的请求不会提前出现在本页；SQLite 观察记录失败也
不会改变已经生成的模型答案、事件流或稳定 API 错误，只会在安全运行日志中记录失败位置。

详情将同一 session 的全部请求投影为一条 Timeline：

```text
客户端请求输入
→ Agent 初始输入准备
→ 模型请求 1
→ 模型请求 1 的工具调用 / 工具结果 / Subagent / Context Worker 事件
→ 模型请求 2…
→ 最近一次模型请求的最终对外文本或异常结束
```

`agent_input` 分别记录 Primary 或 Context Worker 完成 Prompt Preset 后的初始消息数、标签命中数和启动
消息数。Timeline 只在遇到 `kind=model_request` 时递增可见序号；对应的 `model_response`、工具、工具结果、
工具错误、Subagent 和 Context Worker 事件沿用该序号，直到下一个 ModelRequest。`lifecycle` 已由概览中的
时间和最终状态表达，不再重复进入 Timeline。Subagent 一次调用的开始与结束使用相同 `namespace`；
`subagent_name` 标识实际 Subagent，`tool_call_id` 对应主 Agent 发起的 `task` 调用，因此无需建立独立
会话即可确认它属于哪组 session、哪次模型请求和哪次委派。

ModelRequest 在一次性 Prompt Preset 输入处理和其余 LangChain Middleware 之后、Provider 或拦截测试之前
由只观察的 Middleware 捕获。workflow timeline 只保存 Agent 类型与名称、可用调用关联、模型名称、消息数
和工具数，不保存 ModelRequest 正文或 Tool schema。每次 `model_response` 只保存 Agent 身份、Provider
finish reason 及字段来源、LangChain 标准 usage 数字和固定的流完整性计数；Provider metadata、additional
kwargs、finished content blocks 和推理正文均不进入该记录。Tool 事件同样只保存名称、调用 ID、状态和
错误码，不保存参数、结果或文件正文。

打开详情时传输的 Timeline 骨架和步骤 JSON 都遵守上述白名单。客户端输入和最终对外响应仍属于现有
management-only 会话历史，可按明确操作查看或下载；拦截测试下载仍可用于检查完整 Provider-bound
ModelRequest。workflow timeline 不复制第二份敏感内容。所有持久数据继续由同一个 SQLite Session owner
及其保留策略管理，不生成旁路日志文件、JSON sidecar 或消息快照。
当前多模态内容块和附件尚未进入 Agent，后续由独立的输入协议范围处理。

会话记录仅用于观察；下一轮输入仍由客户端提交，不参与上下文合并，也不会在客户端未带 session ID
时根据消息正文猜测会话关系。默认最多保留最近 20 个完整会话，可在本页设置 1–10,000；一个不同的
`X-Agent-Session-ID` 只算一个，无论其中包含多少次请求。最近顺序按该会话最后一次 run 的活动时间
确定。

会话列表的【模型请求数】统计该 session 全部 run 时间线中的 `ModelRequest` 数量，不是客户端请求数。
一次客户端请求没有工具循环时通常调用一次模型；工具调用后再次推理会继续累加。详情不再使用容易混淆
的【轮次】；Timeline 上的数字只表示模型请求序号，概览另行显示客户端请求数。

调小上限会立即、永久地整组删除较早 session 的全部 run，绝不会只留下某个多轮会话的后半段；页面
会在提交前明确确认这个范围。调大不会恢复已删除数据。手动删除同样以整组 session 为单位，并使用
管理台确认层。【删除筛选结果】只在至少一个筛选条件已经应用且存在匹配项时启用；它会由后端按同一
列表 predicate 删除所有匹配的完整 session，不受当前页限制。
