# 安全与部署

deepagent-shell 默认是本机单用户服务。管理 API、自定义 Python、Skill 和映射文件系统都使用服务
进程账户的操作系统权限；虚拟路径校验负责路径边界，当前运行模型为本机单用户。

## 官方入口

从仓库根运行：

```powershell
.\start_server.bat
```

根启动脚本仅在“有效本地配置唯一缺少 management token”时，隐藏输入并确认管理密码，再从
`.env.example` 创建 `data/config/deepagent-shell.env`。配置已有密码时不会覆盖；配置非法或属于远程部署缺项时也不会
自动修正。脚本只使用项目 `runtime/` 内的固定 Python 与依赖，不回退到宿主 Python、Node.js、uv
或虚拟环境。

便携入口只读取显式 data root 中的 `config/deepagent-shell.env`，不读取宿主 `DEEPAGENT_SHELL_*`。它同时清除宿主
`PYTHONHOME`/`PYTHONPATH`，因此复制目录后不会继续引用旧 checkout 或宿主 Python。高级部署入口
必须显式使用 `--mode environment`；该模式才会读取严格的 `DEEPAGENT_SHELL_*` 环境设置，未知同前缀
变量会使启动失败。两种模式都在监听前校验部署设置，所有相对路径都以显式 `--home` 解析。

高级入口示例（开发环境已用 uv 同步依赖）：

```powershell
cd server
uv run python -m deepagent_shell --home .. --data-dir ..\data --mode environment
```

## 设置

| 设置 | 默认 | 作用 |
| --- | --- | --- |
| `DEEPAGENT_SHELL_HOST` | `127.0.0.1` | IP literal 监听地址 |
| `DEEPAGENT_SHELL_PORT` | `19100` | `1..65535` |
| `DEEPAGENT_SHELL_ALLOW_REMOTE` | `false` | 显式允许非 loopback/可信代理部署 |
| `DEEPAGENT_SHELL_MANAGEMENT_TOKEN` | 必填 | 管理网站和 `/api/*` 使用的管理密码 |
| `DEEPAGENT_SHELL_CORS_ORIGINS` | 空 | 明确 HTTP(S) origin 列表；空为关闭 |
| `DEEPAGENT_SHELL_TRUSTED_PROXY_CIDRS` | 空 | 直接可信代理网段 |

启动期只确定一个 data root，再固定派生
`config/state/files/resources/logs`；Windows/source 默认 `<home>/data`，Docker 显式使用
`/app/data`。高级入口可用 `--data-dir` 指定完整 data root。

## 部署闸门

- loopback、remote=false 也必须配置 management token；它就是管理网站的简单密码。
- `/v1/*` 的 API Key 保存在 SQLite，由【首页】设置；没有 Key 时拒绝调用。
- 推理 API 的 running 状态在进程创建和页面启动操作时都会全局静态检查保存的 block、Subagent
  override 和全部公开 Primary。无效配置只会将 `/v1/*` 保持为 stopped；管理外壳、健康检查和
  management 修复入口仍可用。门禁不执行用户 Python、不连接 Provider，也不会把配置问题或
  traceback 写入普通安全响应。
- 每个 Chat Completions 请求只把 blocks、Primary、Subagent override 与 Provider secret 复制到私有
  query-only 内存库；API 调用记录和会话正文不进入配置快照。明文 credential 会在该请求进程内存中存在，
  但不会进入普通响应或日志。
- 非 loopback 或可信代理模式启用 `ALLOW_REMOTE=true`，并在监听前保存 API Key。Docker 首次初始化
  将 API Key 写入 SQLite。
- 管理密码和 API Key 接受非空、不含空格的可打印 ASCII 字符，长度由用户决定，也可以使用相同值。
- token 不进入 URL、页面源码、本地持久浏览器存储、普通错误或日志。

## 资源容量责任

DeepAgent Shell 首版不提供进程级推理并发配额或排队，不为请求正文、Agent 内部 ModelRequest、Session
timeline、虚拟目录文件数或虚拟来源字节数设置隐藏硬上限。每个有效请求独立构造 Agent，虚拟来源按
请求重新完整读取，Session 按当前观察契约保存客户端输入、最终响应和白名单 workflow 统计。部署者应按机器容量、Provider 配额、调用方
并发、输入规模和历史保留设置自行管理资源与费用。

现有鉴权、filesystem containment/no-follow、graph/执行终止和客户端断开取消仍是 correctness 与
安全边界；它们不承担容量规划。若未来发现单个有限输入能够绕过这些终止边界持续产生新工作，应
作为独立 BUG 修复，直接处理根因。

权限范围：

| 路径 | scope |
| --- | --- |
| `/api/health` | 匿名 |
| `/admin`、`/admin/assets/*`、`/admin/favicon.ico` | 匿名静态登录外壳，不含管理数据 |
| 其他 `/api/*` | management |
| `/v1/*` | API |

鉴权使用严格 `Authorization: Bearer <token>`。缺失/错误凭据返回 401，使用另一 scope 的有效
token 返回 403；两者都在读取配置、扫描资源或访问上游前结束。

FastAPI 自动生成的 `/openapi.json`、`/docs` 和 `/redoc` 不属于产品入口，当前不注册；正式说明
以仓库 `docs/` 为准。这不会关闭或改变 OpenAI-compatible `/v1/*` 运行接口。

【系统 / 系统配置】保存 `/v1/*` 的 API Key。普通响应只返回是否配置，不返回明文；未编辑时保持原值，
编辑后清空再保存会清除，随后 API 保持无凭据状态。它不适用于模型 Provider credential。

## 远程发布边界

DeepAgent Shell 的正式入口是普通 HTTP 后端，不内置证书和 TLS，也不根据 `X-Forwarded-Proto` 猜测
外部请求是否安全。受支持的远程拓扑只有一条：

```text
远程客户端 -- HTTPS --> TLS 反向代理/防火墙 -- 私有 HTTP --> DeepAgent Shell
```

也就是说，浏览器或 OpenAI 客户端应只看到反向代理的 HTTPS 地址；DeepAgent Shell 的配置端口不能
直接暴露到公网。强 Bearer 只能防止猜中凭据，不能加密明文 HTTP 上的 Authorization header。
TLS 证书、HTTP 到 HTTPS 跳转、公网端口、IP/网络限制以及需要时的认证失败限速，都由反向代理、
网关或防火墙负责。DeepAgent Shell 不为这些职责增加第二套配置。

反向代理与 DeepAgent Shell 在同一台机器时，优先让 DeepAgent Shell 继续监听 `127.0.0.1`，由代理连接本机
端口；代理位于另一容器或主机时，只绑定受防火墙保护的私有接口。开启远程模式后正式入口会打印
一条警告，提醒当前进程仍是 HTTP 后端；TLS 状态由外部代理和访问入口确认。

## CORS 与代理

CORS 默认不安装。启用时只接受逐项 HTTP(S) origin，不接受 `*`、userinfo、path、query 或
fragment；credentials 关闭。允许 origin 的成功响应以及鉴权、代理校验等失败响应都带同一组
CORS 头，使浏览器能够读取真实 HTTP 状态；未允许 origin 仍不能跨域读取。

uvicorn 代理头处理默认关闭。只有直接对端位于 `TRUSTED_PROXY_CIDRS` 时才解析 `Forwarded`
或 `X-Forwarded-*`；两套格式不能混用。重复、冲突、非法、未知转发头或来自非可信对端的
转发头返回 `400 invalid_proxy_headers`。代理必须覆盖外部传入值。

## Provider credential

model block 的 `credential=null|string` 是 write-only 写入命令：更新时只有 Provider 与 Base URL
都未改变，`null` 才保持已有值；任一连接身份改变且没有新 Key 时清除旧 secret。查询 Provider 模型
目录的请求也必须同时匹配已保存 Provider 与 Base URL 才能复用该 secret。新建时 `null` 表示无 Key，
非空字符串写入或替换。除 Google Vertex AI 外，应用不探测宿主模型 Key 环境变量；Vertex AI 明确只用
官方 Application Default Credentials，model block 不接受普通 Key。

secret 明文保存在同一 SQLite 的 `provider_secrets` 表，model JSON 只保留不透明 reference；
普通 API 只返回 `masked|missing`。复制 model 共享 reference，替换时原子轮换，删除最后一个
引用后清理。当前没有显式 clear 命令，也没有加密 vault。

因此 `data/config/deepagent-shell.env` 中的管理密码、数据库/WAL/SHM 中的 API Key 与 Provider secret、
进程内存、备份软件和同账户进程都可能接触 secret。正式入口在
创建或读取配置文件前会在 POSIX 使用私有权限，在 Windows 写入并复核当前账户 DACL；无法
确认时拒绝继续启动。数据与日志文件沿用同一权限保护。readiness 的 storage 分区报告应用启动时
得到的权限加固结果，状态为 `startup_permissions_confirmed|startup_permissions_unconfirmed`。
远程部署应使用专用低权限账户和专用 data 目录，并另行监控磁盘、目录和 ACL 健康。

## 正文与历史

API 调用记录只在本次配置快照解析出真实 Primary 后，保存 OpenAI 请求 JSON 和实际对外 JSON/SSE
响应；未知 model 与快照失败不会持久化附带正文。拦截测试保存原始 API JSON 与最终
`ModelRequest`；历史会话按请求保存输入 messages、白名单 workflow timeline 和最终对外文本，Tool、
Subagent 只记录身份、调用关联和状态。这三类观察数据中的客户端输入、拦截请求与最终
响应含用户正文，只能通过 management scope 读取，并与配置、安全事件
分表。历史会话详情还从已保存的每次模型响应 usage 汇总整个会话的【输入】、【输出（正文）】和
【输出（思考）】token；正文数包含工具调用等非 reasoning 输出。任一模型调用未上报对应明细时，
该项显示为未上报，不把不完整数据当作总数。

三类正文历史默认保留量都是 20：API 外壳按请求/响应组、拦截测试按捕获记录、历史会话按不同
`X-Agent-Session-ID` 的完整会话计数。事件页可分别设置 API 与拦截记录 1–10,000；历史会话页可
设置 1–10,000 个完整会话。Agent Session 裁剪会整组删除旧会话的全部 run，其他两类删除最旧
超额记录。

日志中心通过 `GET /api/event-feed` 合并四类来源。列表 envelope 只提供排序、筛选和操作需要的摘要
字段；短内容内联为与下载文件同结构的完整 JSON，不再返回供前端重复平铺的字段投影。更长内容只通过
management 鉴权的下载接口读取，事件列表和 SSE 不携带长正文。物理删除记录不会删除配置。日志中心
批量删除由后端直接应用当前来源、级别和全文查询条件，不受前端已加载页数限制；空筛选表示删除四类
来源的全部日志，并需要管理台危险操作确认。

系统日志只返回服务生命周期、配置/凭据操作、认证失败和管理 API 错误的脱敏元数据，磁盘只保留一个
当前文件，默认上限 5 MiB，可在事件页设置 1–1024 MiB。Agent 运行日志的结构化安全条目默认持久保留
最近 20 条，可在事件页设置 1–10,000；服务重启后仍可在日志中心读取。SQLite 是 Agent 运行日志的
唯一持久数据源，列表、下载、删除和保存上限管理同一份记录；进程 stderr 仅提供实时输出，不另写
磁盘副本。`/api/runtime-diagnostics` 管理当前详细模式与持久化条目上限。详细模式增加
lifecycle/tool/Subagent 元数据。

Agent workflow timeline 和 runtime diagnostics 的每类事件都使用显式安全字段白名单；不同 Provider、
Middleware 或 Tool 返回的未知字段和完整 payload 不会透传。客户端/Agent 对话正文、Tool 参数与结果、
文件读写正文不进入这些日志。Prompt Preset 处理前后和 Provider 调用前可以分别记录工作流阶段、Agent
标识与数量统计，但不保存对应消息内容。Agent 运行日志仍只写入上述 SQLite owner，不建立日志文件、
JSON sidecar、消息快照或独立 retention；完整敏感内容只沿用已有 management 鉴权历史与下载通道。

## Health、readiness 与诊断

`/api/health` 只表示 Web 进程可响应，不探测具体 Provider。`/api/readiness` 分别报告 security
settings、启动时 storage 权限确认、DeepAgents 和六个内置 LangChain Provider integration 的依赖状态；
依赖可用性在生成报告时检查，storage 不伪装成实时磁盘状态，也不连接 Provider。

拦截测试由【系统 / 系统配置】持久保存；详细诊断由日志中心【保存策略】持久保存，默认关闭。两者更新
后立即作用于当前 runtime，服务重启后从 SQLite 恢复用户保存的状态。当前能力事实以真实 Agent runtime、
`/api/readiness` 和对应行为测试为准。

## 脱敏与安全事件

统一脱敏处理 secret/token/password/Authorization、URL userinfo、消息正文、tool 参数、
Provider 原始响应、traceback 和宿主绝对路径。公开错误只保留稳定 code、说明和必要 request
ID，不调用未知对象的 `repr()`。Provider SSE 已经开始后若 curl transport 中断，management-only
运行诊断额外保留数值 `curl_code` 和固定 curl 枚举名；原始异常文案、请求 URL 和响应内容仍不进入
诊断或公开错误。

`data/logs/security-events.jsonl` 只记录启动/shutdown、设置、配置变更和 provider secret
轮换/清理等白名单元数据，不记录 payload、消息或 traceback。管理台通过 management-only
`/api/event-feed?source=system` 查询这组脱敏事件。系统日志只使用当前
`security-events.jsonl` 文件，不创建备份；事件页【保存策略】可以把最大保存大小设置为 1–1024 MiB，
默认 5 MiB。当前文件超过新上限时会清空并从下一条事件继续记录。

SQLite 配置结果是管理操作的权威结果，安全事件是提交后的附加观察记录。服务已经成功初始化后，
若事件文件临时不可写或轮转失败，配置操作仍返回数据库的真实结果，并在现有运行诊断中记录脱敏的
`security_event_record_failed`；不会把已经成功的创建、修改、删除或 Key 轮换改报成 500。启动时
连日志目录和当前文件都无法创建或实施权限保护，仍属于正式入口的启动失败。

## 示例

本地监听至少需要管理密码；标准启动脚本会安全创建 `data/config/deepagent-shell.env`，用户 API Key 可以随后在
【系统 / 系统配置】设置：

```powershell
.\start_server.bat
```

同机 TLS 反向代理属于高级环境模式。先在本地模式的【系统 / 系统配置】保存 API Key，再开启远程
设置。下面示例只为管理网站生成一个随机密码；反向代理应单独监听公开的 443，并把请求转到本机
当前默认的 19100：

```powershell
cd server
$env:DEEPAGENT_SHELL_HOST = '127.0.0.1'
$env:DEEPAGENT_SHELL_ALLOW_REMOTE = 'true'
$env:DEEPAGENT_SHELL_MANAGEMENT_TOKEN = uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:DEEPAGENT_SHELL_TRUSTED_PROXY_CIDRS = '127.0.0.1/32'
uv run python -m deepagent_shell --home .. --data-dir ..\data --mode environment
```

若代理不发送 `Forwarded`/`X-Forwarded-*`，可以不配置 `TRUSTED_PROXY_CIDRS`。若配置了，网段必须
只包含直接代理，且代理必须覆盖客户端传入的转发头。不要为了省事把任意公网网段设为可信代理。

不要提交真实 token 或含 secret 的 `data/config/deepagent-shell.env`。应用只读取当前 schema，未经用户授权不迁移、删除
或改写 `data/`。
