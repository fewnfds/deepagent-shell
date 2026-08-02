# API Server

右上角 navbar 在所有管理页面显示 API Server 状态并提供启停；【首页】显示接入地址和配置报警。它们共同
控制当前 FastAPI 进程中的单实例 `/v1/*` 推理入口。API Key 与请求设置统一放在【系统 / 系统配置】。
启动/关闭只改变推理 API 是否接受请求，
不停止管理台、进程或监听 socket。新数据库在空仓库静态门禁通过后默认开启。

navbar 使用带轻微红/绿光晕的停止/运行图标表达当前业务状态；悬停提示当前状态和点击后的启停动作。

点击“启动”时，服务端先使用当前统一静态规则全局检查保存的 block、Subagent override 和全部将作为
model 公开的 Primary；任一 contract、required、UUID 引用、依赖、Subagent 最终引用或静态
工具名有误，启动返回完整管理报告并保持 stopped。该门禁不构建 Agent、不 import 用户
Tool/Middleware，也不连接 Provider；对已选择自定义 Tool 只做不执行代码的 AST 名称发现，文件缺失、
动态名称或 import 状态仍留给真实请求检查。没有 Primary 时可以开启并返回空 models 列表。管理网站、
`/api/health`、配置仓库和修复页面始终保持可用。

首页同时读取与启动门禁相同的仓库校验报告。报告无效或暂时不可用时才显示【配置报警】；报警默认
收起为包含问题数量的摘要，展开后逐项列出所属配置、问题位置、技术路径、原因和修复方式。组件问题的
所属配置同时显示具体组件类型和配置名称。已从当前版本移除的组件记录无法再进入编辑器，可在配置仓库
对应报警中确认删除；其他历史组件即使能载入修复编辑器，在用户保存成当前严格结构前仍保持报警，也
不能通过 API Server 启动门禁或真实 Agent 装配。

若上次状态为 running，管理进程重新启动时也会先执行同一静态门禁；历史无效配置会把推理 API
安全切回 stopped，管理应用继续启动。API Server 运行期间所有配置 CRUD 继续开放；通过管理
API 保存的新值会用于后续请求，已经构造完成的 Agent 不会被改写。若运行期间通过外部方式留下无效
数据，API Server 状态不会伪装成持续校验器，后续相关请求会在 Provider 前安全失败。

## OpenAI-compatible API

`GET /v1/models` 发布当前保存的 Primary 名称。名称是公开 model ID，内部 UUID 不暴露；
管理 API 或管理台对已载入 UUID 执行 PUT 改名后，旧名称立即失效。只有明确新建或从配置仓库复制
Primary 才会生成另一份 UUID。

`POST /v1/chat/completions` 在每次 Primary `create_deep_agent()` 前，以一次 SQLite 读事务把 blocks、Primary、
Subagent override 和 Provider secret 复制到私有 query-only 内存库。公开 model 名称解析、Primary
UUID、静态装配和 credential 都使用这同一份请求快照；捕获完成后的数据库修改只影响后续请求。
随后构造 selected model、tools、Middleware 和同步 Subagent child graph，并调用真实
`create_deep_agent()`。请求会复用
保存/启动使用的静态规则，再检查当前磁盘、Skill 元数据、选中用户 Python、最终 Tool/Middleware 名称
和构造结果；这些准备期问题都会在 Provider 前返回稳定 code 与安全说明。已经成功准备的对象不会
为了校验再构造一次，未选择的能力不会读取或执行。Provider、Tool 或 graph 真正执行后的失败仍使用
各自的 runtime 错误类别。当前只接受 system/user/assistant 的纯文本消息；客户端应在每次请求中携带
需要的完整历史。

请求快照只保护数据库配置一致性。用户 Custom Tool 源码、`data/resources/skills/` 和 filesystem 映射是实时
外部资源，不复制、不锁定；运行中修改它们可能被当前或后续 Agent 观察到，维护时机由使用者负责。

DeepAgent Shell 不对请求正文设置自定义字节、字符或 token 上限，也不会截断、压缩客户端提交的正文。
【系统 / 系统配置】可以设置一次请求的【初始消息条数上限】，默认 1000，可设 1–10,000。服务端只数
客户端顶层 `messages[]` 的项目数：等于上限时完整进入后续流程，超过时返回
`input_messages_too_many`，整次请求不进入 Agent，不会只取前 N 条。Agent 内部后续产生的
ModelRequest 不受此设置影响。

例如上限为 1000 时，包含 1000 条消息的请求会原样继续；包含 1001 条消息的请求会整体返回 422，
第 1–1000 条也不会被拿去生成回答。当前 runtime 仍只接受 system/user/assistant 的纯文本字符串
消息；文档文字可以作为字符串内容提交，图片、音视频、文件 URL/base64 或其他多模态消息结构尚不
受支持，会返回明确的不支持错误。部署使用的反向代理仍可能有独立请求上限。

首次调用 Primary 时可以不传 `X-Agent-Session-ID`，服务端会生成该值并在响应头返回。客户端
希望把下一次请求归入同一组多轮记录时，应原样带回该响应头；这只影响观察页面的分组，不会
让服务端自动补全或改写 `messages[]`。

`stream=true` 返回 Chat Completions SSE，`stream=false` 消费同一 runtime 字符串流并返回
普通 JSON；两者都严格使用 Primary 必选的 output mode。首版只消费 `model`、`messages` 和
`stream`；OpenAI 客户端
携带的其他顶层字段可以保留在请求中，但不会传给 Provider，也不会覆盖模型组件中的参数。
流式或非流式请求在客户端断开后都会取消并等待当前 Agent 执行结束，不让 Provider 或工具任务在
无客户端接收结果时继续运行。

成功响应的 `choices[0].finish_reason` 来自最后一次 Primary 模型响应，不再固定写成 `stop`。如果
Provider 没有提供原因则明确返回 `unknown`；`length`、`content_filter`、最终 `tool_calls`、未知值等
非正常完成还会在顶层 `deepagent_shell.termination` 返回 `status/category/source/message` 结构。流式响应
把该结构放在 `[DONE]` 前的最终 chunk，非流式响应放在最终 JSON。运行错误继续使用既有 `error` 结构。
DeepAgent Shell 不因未知原因或诊断差异主动取消 graph；只有客户端断开/用户停止会取消正在执行的 Agent。

Provider 通过 LangChain usage 上报 reasoning token 时，两种响应都会保留标准
`usage.completion_tokens_details.reasoning_tokens` 数值；流式响应位于 `[DONE]` 前的最终 chunk。该数值
累计一次 Agent 请求中的全部模型调用。字段缺失表示 Provider 没有上报，不能按 `0` 解读；明确返回
`0` 才表示 Provider 报告本次没有使用 reasoning token。

DeepAgent Shell 不提供进程级推理并发配额、请求排队或容量拒绝。多个有效请求可以同时构造并运行各自的
Agent；部署者应按机器容量、Provider 配额和调用方行为自行控制并发与费用。有限但较慢或较多的请求
属于部署容量，不会由应用自动截断或排队。

## API Key

【系统 / 系统配置】提供一个【API 密钥】密码框：已存在密钥时显示 `••••••••`，未配置时提示输入。
未编辑时保存会保持当前 API Key；输入新值后保存会替换，编辑后清空再保存会清除。SQLite 中保存的值
用于 `/v1/*` 鉴权。没有 Key 时 `/v1/*` 拒绝调用。

Key 是 write-only：页面和普通 API 显示配置状态，不返回明文。调用者使用
`Authorization: Bearer <API Key>` 访问 `/v1/*`；管理网站和 `/api/*` 使用管理密码。两项凭据可以使用
相同值，scope 仍由请求路径决定。

管理密码和 API Key 的长度由用户决定，内容使用非空、不含空格的可打印 ASCII 字符。远程启用前保存
API Key；远程运行时移除 Key 会被拒绝。

navbar 状态图标与启动/关闭动作使用同一服务端状态。`running` 表示已通过门禁并开启，`stopped` 表示关闭；
关闭时 `/v1/models` 和新进入的 `/v1/chat/completions` 返回 `api_server_stopped`，管理 API 仍可用。
已经完成快照并开始执行的请求不因开关关闭而取消，会继续返回自己的结果。

【API 接入地址】直接列出 Base URL、Models 和 Chat Completions。页面不展示后端字段路径或固定
runtime 实现值。

系统配置页使用一个页面级保存动作提交 API Key、初始消息条数上限和其他系统字段。未编辑 API Key 时，
修改消息条数上限不会替换或移除它；输入框和服务端都要求 1–10,000 之间的整数。该值持久化到 SQLite，
重启管理进程后继续生效。页面不重复展示限制说明，完整行为以本节为准。

## API 调用记录

只有本次配置快照能够把非空 `model` 解析为真实 Primary 后，执行路径才允许保存 API 调用记录。
未知 model 返回 `model_not_found`，其附带正文不会进入 API 历史、Agent Session 或拦截记录；配置
快照本身失败时也不保存正文。非法 UTF-8/JSON、非对象或缺少 model 同样发生在历史记录起点之前。
已解析到真实 Primary 后，初始消息超限、其他消息校验、配置准备和 runtime 失败仍会保存 wire，便于
管理员确认一次真实 Agent 请求为什么被拒绝。记录正文含义如下：

- “接收 · OpenAI Request”是外部客户端交给 deepagent-shell 的原始 UTF-8 JSON；
- “发送 · OpenAI Response”是 deepagent-shell 实际返回的 JSON 或 SSE wire；
- 内容范围限于外部客户端与 DeepAgent Shell 之间的 wire；Provider 调用和 Agent runtime 事件由各自来源记录。

记录还包含 request ID、时间、公开 model、当时的 Agent 名称、状态、HTTP 状态、Content-Type
和稳定错误码。它不保存 Authorization、客户端地址、traceback、Provider 原始响应或内部
tool/Subagent 事件。

API 调用记录是次要观察数据。SQLite 写入失败时，原本的模型答案、SSE 事件或 API 错误保持不变；
失败位置只进入不含正文的安全运行日志。

在【系统 / 日志中心】选择 API 调用来源即可查看记录。折叠摘要显示本地时间、结果和级别；展开短记录
后直接显示包含 request ID、Agent/model、HTTP 状态、错误码及请求/响应 wire 的完整 JSON，不再把
这些字段额外平铺一遍。全文查询仍覆盖 request ID、model、Agent、状态、错误码及保存的请求/响应正文。

短记录直接显示与下载文件同结构的 UTF-8 JSON；更长的记录通过操作菜单中的【下载完整条目】取得，
下载文件包含完整请求和响应 wire。筛选 Card 的【批量删除】会删除后端全部匹配项，不限于当前加载页。

API 调用默认最多保留最近 20 组请求/响应，事件页可设置 1–10,000。保存较小上限后，服务端立即永久
裁剪最旧的超额记录；调大不会恢复已删除数据。

拦截测试开启时，API 调用记录仍保存原请求和固定拦截响应；最终 `ModelRequest` 另存在拦截记录。

API 调用记录描述客户端与 DeepAgent Shell 之间的 wire。Agent 内部 ModelRequest、工具调用链和安全错误
位置分别由拦截记录、历史会话和运行日志提供，可在[日志中心与历史会话](runtime-observability.md)
中查看具体边界。
