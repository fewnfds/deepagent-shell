# Agent Shell server

`server/` 是 Agent Shell 的 FastAPI 后端和 Deep Agents runtime。可编辑前端源码位于根目录
`frontend/`，production 前端产物由后端托管。

主要接口：

- `/admin`：管理台；
- `/api/health`、`/api/readiness`：存活与就绪状态；
- `/api/catalog`、`/api/blocks/*`：组件目录与 CRUD；
- `/api/main-agents`、`/api/subagents`：Agent 配置；
- `/api/tools/custom`、`/api/middlewares/custom`、`/api/skills`：用户资源发现；
- `/api/file-manager/*`、`/api/system/settings`：数据与实例设置；
- `/api/event-feed`：系统日志、请求级运行错误诊断与显式拦截测试记录；
- `/v1/models`、`/v1/chat/completions`：OpenAI-compatible 推理接口。

每个推理请求从单次 SQLite 快照解析配置，再通过 `deepagents.create_deep_agent()` 构造 Main Agent 和
同步 Subagent。用户资源文件在装配时重新校验和物化。多轮消息由客户端提交；当前不提供 Workflow 执行历史、
聊天记忆或 checkpoint/resume。

## 运行与开发

普通源码运行从仓库根执行：

```powershell
.\start_server.bat
```

新实例默认监听 `127.0.0.1:19100`，数据库默认位于
`data/state/agent-shell.sqlite3`。启动参数 `--home` 与 `--data-dir` 可分别指定应用目录和数据目录。

后端开发：

```powershell
cd server
uv sync --extra dev
uv run pytest ..\test\<domain>\test_relevant_module.py -q
```

完整说明见根 [README](../README.md)、[用户指南](../docs/user-guide/README.md)和
[开发与发布](../docs/development-and-release.md)。
