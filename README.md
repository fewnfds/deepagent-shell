# Agent Shell

Agent Shell 是 `agent-shell` 的升级项目：保留本机管理台、配置持久化、OpenAI-compatible API
和运行观测等可复用能力，将 Agent harness 从 LangChain `create_agent()` 升级为 Deep Agents
`create_deep_agent()`。用户在管理台中保存模型、提示词、
工具、Middleware、文件系统、Skill 和同步 Subagent，再把一份 Primary Agent 作为
OpenAI-compatible model 调用。

项目的新内核只使用 `deepagents.create_deep_agent()` 构造 Agent。Deep Agents 默认提供 filesystem、
subagent、summarization、tool-call repair 和适用模型的 prompt caching；本项目显式选择的 Tool、Skill、
Backend、Subagent 和额外 Middleware 再合入该默认 harness。未被配置引用的用户资源仍不读取、不导入、
不实例化。Primary 和同步 Subagent 的构造内核已经迁移；后续功能继续按模块核对并收口，不把旧项目
说明或历史记录当作当前运行事实。

## 当前能力

- 随服务本地发布的 Vue 3 管理台、FastAPI 管理 API 与 SQLite 持久化；管理台支持中文/英文与
  云白、深海、青玉、暮紫四套颜色主题；
- 模型、系统提示词、文件系统、待办计划、自定义工具、Skill、自定义 Middleware、输出模式、
  异常重试、提示词预设和 Subagent 十一类组件；
- Primary Agent、可复用 Subagent 覆写、统一配置仓库与 UUID 删除保护；
- OpenAI-compatible `/v1/models`、流式/非流式 `/v1/chat/completions` 和 API 调用事件；
- 每次 Chat Completions 在 `create_deep_agent()` 前捕获最新已提交的配置与 Provider secret 内存快照，
  新请求使用新配置，已构造 Agent 不受后续数据库修改影响；
- 汇总 API 调用、拦截记录、脱敏系统操作和 Agent 运行日志的滚动事件信息流，长条目支持鉴权下载；
- 按 `X-Agent-Session-ID` 分组、以模型请求编号的历史会话 Timeline；
- selected custom tools、Todo、filesystem/Skill、自定义 Middleware 与同步 Subagent 的真实
  Agent 循环；
- LangChain v3 事件到自定义文本流的输出模式；
- 可选的整块提示词移动，以及在 Provider 前短路并展示最终 `ModelRequest` 的拦截测试；
- write-only provider credential、管理/API 鉴权、部署闸门和统一脱敏。

当前仍在首版收口阶段。仓库提供 `dev` 滚动源码和 `main` 稳定源码两个通道；Windows ZIP 与 GHCR
Docker image 只在维护者从 `main` 创建明确版本 tag 后构建，不要求每次稳定源码更新都发布二进制产物。

## 快速开始

支持 Windows 10/11 x64。需要持续获取最新代码的用户安装 Git 和 Node.js 22（含 npm），直接 Clone
滚动 `dev` 分支：

```powershell
git clone --branch dev https://github.com/fewnfds/deepagent-shell.git
cd deepagent-shell
.\start_server.bat
```

干净 Clone 一开始不包含 `data/` 或 `runtime/`。需要搬入当前版本的旧实例时，先在停机状态复制完整
`data/`；否则首次启动会创建缺失的数据目录。启动不会覆盖已有的有效 `data/`。首次源码启动还会
联网准备固定 Python runtime、锁定前端依赖和 production 管理台。以后只有 runtime 输入或前端输入
变化时才刷新对应部分，普通重复启动会直接复用。停止服务后更新：

```powershell
git pull --ff-only
.\start_server.bat
```

运行 Clone 自己的 `data/` 被 Git 忽略，pull 不会覆盖配置、数据库、用户资源和日志。不要在同一个运行
目录中切换 `main/dev`，也不要手工修改运行 Clone 的源码。启动脚本会按当前 lock 和源码指纹准备
运行所需内容，完整规则见[源码运行、Debug 与发布流程](docs/development-and-release.md)。

只希望跟随已经确认稳定的源码时，改为 Clone 默认 `main` 分支。`dev` 的完整改动经过实际使用确认后
才 merge/fast-forward 到 `main`。

没有已有配置时，控制台首次启动会要求输入两次管理网站密码，并创建
`data/config/agent-shell.env`；输入不会显示，后续启动直接使用已有配置。这个密码用于管理网站
和 `/api/*`。在【系统 / 系统配置】设置 `/v1/*` 使用的 API Key；两项凭据可以使用相同值。打开
<http://127.0.0.1:19100/admin>。端口始终以该实例配置为准；19100 只是新实例当前默认值。

## 稳定发行物

只有 [GitHub Releases](https://github.com/fewnfds/deepagent-shell/releases) 中实际存在的版本才提供受支持的
Windows ZIP 和对应 GHCR image；源码中的版本字段不代表相应发行物已经发布。

Windows ZIP 解压到可写目录后双击：

```powershell
.\start_server.bat
```

ZIP 已包含固定 CPython、锁定生产依赖、Agent Shell wheel 和构建好的管理台。普通用户不需要 Git、
Python、Node.js、uv、编译器或首次启动网络。便携入口只读取当前目录的
`data/config/agent-shell.env`，忽略宿主 `AGENT_SHELL_*`、`PYTHONHOME` 和 `PYTHONPATH`，因此复制或
移动目录后会使用新目录自己的 `data/`。`runtime/` 是可重新生成的临时运行态。端口被占用或被
Windows 保留时，脚本会让用户选择可用端口或取消启动；已有监听进程时还可明确选择关闭它。

## Docker 部署

正式发布后，Linux amd64/服务器可使用 GitHub Container Registry 中相同版本的 image：

```text
ghcr.io/fewnfds/deepagent-shell:<version>
```

从对应 GitHub Release 的源码包或 tag 获取仓库内容。Windows 运行 `./start_docker.ps1`，Linux
运行 `sh ./start_docker.sh`；首次启动会创建同一 `data/config/agent-shell.env`，并把一个宿主
`data/` 映射为容器 `/app/data`。默认从宿主机访问 <http://127.0.0.1:19100/admin/>；容器不包含
Node、uv 或编译工具。配置、端口和持久化说明见 [Docker 部署](docs/docker.md)。

## 源码与自行构建

稳定 `main` 源码可以这样取得：

```powershell
git clone https://github.com/fewnfds/deepagent-shell.git
cd deepagent-shell
```

构建代码完全公开。需要从源码重建正式 ZIP 的开发者，在 Windows x64 上安装 Node.js 22（含 npm），
然后从仓库根运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\build_portable.ps1
```

构建脚本执行 `npm ci` 和前端门禁，随后自行下载并校验锁定 uv/CPython，不要求预装 Python 或 uv。
结果位于 `release/agent-shell-windows-x64.zip`；包内同时包含 `release-manifest.json`、
`SBOM.spdx.json`、`THIRD_PARTY_NOTICES.md` 与上游提供的许可证文件。这里的 Node.js 只属于构建环境，
只供维护者构建发行物。完整输入、产物和校验说明见[从源码构建 Windows 发行包](docs/building-windows-release.md)。
滚动源码运行、显式 Debug、版本更新、tag、GitHub Release 和发布后复验见
[源码运行、Debug 与发布流程](docs/development-and-release.md)。

默认数据库是 `data/state/agent-shell.sqlite3`。配置、数据库、用户文件/资源和日志都在 `data/`；
不要用删除数据库代替页面操作。停止实例后复制完整 `data/`，即可给当前版本的新安装或新容器使用。
项目不提供初始 Skill、Custom Tool 或 Custom Middleware 数据；这些用户资源都由当前实例在
`data/resources/` 中维护。

## 调用

先在【组件】分别保存模型、文件系统和输出模式，再在【Agent / Primary Agent】选择这三项必选配置。
页面会显示服务端草稿校验结果；点击保存后，服务端仍会重新校验，通过后才会落库。Primary 名称
就是公开 model ID：

```http
GET /v1/models
POST /v1/chat/completions
```

调用者使用 `Authorization: Bearer <API Key>`；该 Key 在【首页】保存，用于 `/v1/*`。
管理网站和 `/api/*` 使用管理密码，两项凭据可以使用相同值。

当前多轮对话由客户端在每次请求中提交完整 `messages[]`。事件信息流中的 API 调用来源用于查看实际
收发；Agent 的运行输入始终来自当前请求的 `messages[]`。

API Server 运行期间仍可维护配置。每次新请求都会从同一个请求级内存快照解析公开 model 名称、
Primary/Subagent 装配和 Provider credential；Custom Tool、Skill 与 filesystem 路径仍是实时外部资源。

服务端会在 Primary 响应头返回 `X-Agent-Session-ID`；客户端带回该值时只会把多次请求归入同一
观察记录，不会改变上述消息权威边界。

## 目录

```text
data/                         首次启动创建或由用户停机复制，不属于源码
  config/                     启动配置
  state/                      SQLite 与 WAL/SHM
  files/                      普通用户文件
  resources/                  用户 Skill、Tool 和 Middleware
  logs/                       系统与 Agent 运行日志
runtime/                      启动或构建生成的可清理运行态，不属于源码
frontend/                     Vue SFC、TypeScript 与前端构建配置
server/src/agent_shell/           后端、runtime 与已构建管理台产物
packaging/                    公开的自举、发行、SBOM 与校验代码
.test/                        公开的稳定行为测试
docs/                         当前版本使用说明
```

## 文档

- [用户指南](docs/user-guide/README.md)
- [组件页面](docs/wizard-pages/README.md)
- [Agent 页面](docs/agent-pages/README.md)
- [Docker 部署](docs/docker.md)
- [源码运行、Debug 与发布流程](docs/development-and-release.md)
- [数据、文件管理与系统配置](docs/user-guide/system-management.md)
- [安全与部署](docs/security-and-deployment.md)
- [文档索引](docs/README.md)

## 开发

后端使用 Python 3.11+、FastAPI、SQLite、LangChain；DeepAgents 是精确锁定的必需 runtime 依赖。
前端唯一源码位于根 `frontend/`，使用 Vue 3 SFC、Vite、strict TypeScript、Vue Router、vue-i18n
以及 AdminLTE 4.1 / Bootstrap 5.3；正式发行时，FastAPI 托管构建进 Python wheel 的 production
前端产物。

后端开发安装 uv 后，从 `server/` 同步并运行与改动最接近的隔离测试：

```powershell
uv sync --extra dev
uv run pytest ..\.test\<domain>\test_relevant_module.py -q
```

滚动源码 Clone 的正常运行入口是：

```powershell
.\start_server.bat
```

脚本使用项目自带的 Python 和固定第三方依赖，后端直接载入当前 `server/src/`；前端输入发生变化时
才从锁定依赖生成 production 管理台，随后由同一个 Python 端口提供。它不构建 ZIP、Docker、SBOM
或应用 wheel。源码 Clone 因此前端准备阶段需要 Node.js 22，正式 ZIP 运行不需要。

只有连续修改前端并需要 Vite HMR 时，才显式运行
`packaging/development/start_dev.ps1`；它使用自动临时端口和隔离临时 data，只用于前端开发调试。
提交前按改动范围选择检查：

```powershell
npm run lint
npm run typecheck
npm test
npm run build
```

`npm run build` 生成被 Git 忽略的 `server/src/agent_shell/frontend_dist/`；源码正常运行在输入变化时
自动执行它，正式 Windows ZIP 与 Docker image 再把当前源码和该产物冻结进发行物。源码输出、
production build 和发行包各自只有一个明确职责。

稳定测试代码与脱敏固定 fixture 位于 `.test/` 并随源码公开；本机测试数据、数据库、日志、缓存和
`.docs/` 开发资料不会进入 Git。当前处于 0.x 快速开发阶段，以源码和现行契约为准；除非单独宣布
兼容范围，不保留旧 schema、旧字段或旧 API 的兼容层。

开发和发布不要凭历史命令猜测，统一按[源码运行、Debug 与发布流程](docs/development-and-release.md)执行。
