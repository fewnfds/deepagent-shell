# Agent Shell

Agent Shell 是一个本地 Deep Agents 配置与运行服务。它提供 Vue 管理台、持久配置、
OpenAI-compatible API、运行日志和历史会话，并使用 `deepagents.create_deep_agent()` 构造
Primary Agent 与同步 Subagent。

## 功能

- 管理模型、系统提示词、文件系统、待办计划、自定义工具、Skill、自定义 Middleware、输出模式、
  异常重试和委派能力；
- 为每个 Agent 身份挂载可声明第三方依赖的 Python 自动化插件，接入 LangChain 原生 Hook 与 Shell 生命周期；
- 通过 Primary Agent 组合组件，通过可复用 Subagent 实体定义路由身份、能力策略和下级引用；
- 提供 `GET /v1/models` 与流式/非流式 `POST /v1/chat/completions`；
- 支持 OpenAI、Anthropic、Google GenAI、Google Vertex AI、DeepSeek 和 xAI；
- 使用 SQLite 保存配置、凭据状态、API 调用记录、拦截记录、运行日志和历史会话；
- 在日志中心统一查询事件，在历史会话中按请求查看模型、工具与 Subagent 时间线；
- 提供文件管理、系统设置、管理认证、推理 API Key、CORS、可信代理与远程部署闸门；
- 提供可移动的 Windows 源码 Clone 和 Linux amd64 Docker 部署方式。

Deep Agents 的 filesystem、subagent、summarization、tool-call repair 等 harness 能力由上游负责。
Agent Shell 负责读取当前配置、准备 backend/skills/subagents/tools/middleware，并把运行事件投影为公开输出。

## 快速开始

Windows 10/11 x64 的滚动源码用户需要 Git 和 Node.js 22：

```powershell
git clone --branch dev https://github.com/fewnfds/deepagent-shell.git
cd deepagent-shell
.\start_server.bat
```

首次启动会准备项目自己的 Python runtime，并要求设置管理密码。打开
<http://127.0.0.1:19100/admin>；实际端口以 `data/config/agent-shell.env` 为准。

更新运行 Clone：

```powershell
git pull --ff-only
.\start_server.bat
```

`data/` 保存实例配置和用户数据，`runtime/` 保存可重建运行态，两者都不由 Git 更新。更新或迁移前
先停止服务；Windows 实例可以整体移动到新的可写目录，若只迁移数据则复制完整 `data/`。

## 配置第一份 Agent

1. 在【组件】创建一个模型和一个输出模式；这两项是 Primary 的必选组件。
2. 按需创建系统提示词、文件系统、工具、Skill、Middleware、重试或委派能力。
3. 在【Agent / Primary Agent】选择组件并保存。Primary 名称就是公开 model ID。
4. 在首页设置 `/v1/*` 使用的 API Key，并启动 API Server。

```http
GET /v1/models
Authorization: Bearer <API Key>
```

```http
POST /v1/chat/completions
Authorization: Bearer <API Key>
Content-Type: application/json

{
  "model": "my-agent",
  "messages": [{"role": "user", "content": "Hello"}],
  "stream": false
}
```

客户端每次请求提交完整 `messages[]`。`X-Agent-Session-ID` 用于把多次请求归入同一历史会话，
不承担聊天记忆；服务端响应也会返回该 header。

## 发行与部署

稳定源码位于 `main`，滚动源码位于 `dev`。

- Windows：Clone 需要的分支，运行 `.\start_server.bat`；首次启动自动准备固定 Python runtime。
- Docker：使用 `ghcr.io/fewnfds/deepagent-shell:<version>`，把宿主 `data/` 映射到 `/app/data`。

详情见 [Docker 部署](docs/docker.md)和[开发与发布](docs/development-and-release.md)。

## 数据目录

```text
data/
  config/       启动配置
  state/        SQLite 数据库
  files/        用户文件
  resources/    Skill、自定义工具、自定义 Middleware 和自动化脚本
  logs/         系统与 Agent 运行日志
runtime/        可重建的 Python runtime、缓存与临时文件
frontend/       Vue 3 前端源码
server/src/     FastAPI、配置与 Agent runtime 源码
packaging/      启动、构建与发布脚本
.test/          稳定行为测试
docs/           当前版本公开说明
```

## 文档

- [用户指南](docs/user-guide/README.md)
- [组件说明](docs/wizard-pages/README.md)
- [Agent 说明](docs/agent-pages/README.md)
- [自动化插件](docs/user-guide/automation.md)
- [安全与部署](docs/security-and-deployment.md)
- [开发与发布](docs/development-and-release.md)
- [全部文档](docs/README.md)

## 开发

后端使用 Python 3.11+、FastAPI、SQLite、LangChain 与 Deep Agents；依赖由 `server/uv.lock` 锁定。
前端使用 Vue 3、strict TypeScript、AdminLTE 4.1 与 Bootstrap 5.3。

```powershell
cd server
uv sync --extra dev
uv run pytest ..\.test\<domain>\test_relevant_module.py -q
```

```powershell
cd frontend
npm ci
npm run lint
npm run typecheck
npm test
```

开发、Debug、分支与发布规则统一见[开发与发布](docs/development-and-release.md)。
