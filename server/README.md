# Agent Shell server

这是 `agent-shell` 的 FastAPI 服务，包含管理 API 与真实 LangChain Agent runtime。可编辑前端源码
位于仓库根 `frontend/`；源码 Clone 按输入指纹生成 production 管理台，正式 wheel/image 冻结同类
产物，服务端不在请求时编译页面。Vite 只用于显式前端 Debug。

主要入口：

- `/admin`：管理台；
- `/api/health`、`/api/readiness`：liveness 与分层 readiness；
- `/api/blocks/{block_type}`：十一类组件 CRUD；
- `/api/primary-agents`、`/api/subagent-overrides`：Agent 装配 CRUD；
- `/api/tools/custom`、`/api/middlewares/custom`、`/api/skills`：AST/frontmatter 静态资源发现，
  统一返回 `{catalog, errors}` 且不执行未选择内容；
- `/v1/models`、`/v1/chat/completions`：OpenAI-compatible 推理 API；
- `/api/event-feed`：API 调用、拦截、系统日志与 Agent 运行日志的统一读取和长条目下载；
- `/api/interception-test`：Provider 前拦截开关；
- `/api/runtime-diagnostics`：持久详细诊断开关与持久运行日志保存上限；
- `/api/agent-sessions`：按 session 聚合的 Agent 请求时间线；
- `/api/file-manager/*`：四个用户数据 scope 的文件/文件夹管理；
- `/api/system/settings`：不回显 secret 的启动配置读取与原子保存。

Primary runtime 按明确选择构造 OpenAI-compatible model、tools、Middleware、同步 Subagent、
提示词注入和输出模式；Primary 与同步 Subagent 统一调用 `deepagents.create_deep_agent()`。服务提供轻量只读会话时间线，
但不提供持久聊天记忆、通用 trace/span 平台、异步 Subagent 或兼容旧 schema 的读取层。
每个 Chat Completions 请求在 model 解析和 Agent 构造前，以单次 SQLite 读事务把四类配置数据复制到
query-only 内存库；运行装配不在多个时刻读取 live 配置。

## 运行

推荐从仓库根目录使用启动脚本：

```powershell
.\start_server.bat
```

它会在项目 `runtime/` 内准备并只使用固定的自包含 Python 环境；普通用户不需要安装 Python 或 uv。
首次启动会在控制台要求输入两次管理网站密码，并自动创建
`data/config/agent-shell.env`；已有密码不会被覆盖。

源码仓库中的启动脚本只从 `runtime/` 使用 Python 与第三方依赖，Agent Shell 后端直接从当前
`server/src/` 载入；前端输入变化时按锁定依赖生成被 Git 忽略的 `frontend_dist/`，随后由同一个
Python 服务端口托管。正式 Windows ZIP 不包含 `server/src/`、Node.js 或源码准备脚本，同一启动脚本
直接运行包内冻结的 Agent Shell wheel 和前端。

后端开发安装 uv 后，从 `server/` 运行职责最接近的隔离测试：

```powershell
uv sync --extra dev
uv run pytest ..\.test\<domain>\test_relevant_module.py -q
```

正常管理页面使用仓库根 `start_server.bat`。只有需要 Vite HMR 时才显式调用
`packaging/development/start_dev.ps1`，它使用隔离临时 data 和自动临时端口；不要为普通后端测试
启动持久源码实例。

新实例默认监听 `127.0.0.1:19100`，数据库位于仓库根目录的
`data/state/agent-shell.sqlite3`。application home 与 data root 分别由 `--home`、`--data-dir`
确定。环境变量示例见根 [`.env.example`](../.env.example)，完整部署约束见
[安全与部署](../docs/security-and-deployment.md)。

management token 是管理网站的简单密码，本地监听也必须配置；启动脚本的首次引导只创建这个密码，
用户调用 `/v1/*` 使用 inference API Key；它允许与管理密码填写相同值。

项目使用说明见根 [README](../README.md) 与 [用户指南](../docs/user-guide/README.md)。
源码运行、显式 Debug、依赖刷新、验证和正式 tag/发布步骤统一见
[源码运行、Debug 与发布流程](../docs/development-and-release.md)。
