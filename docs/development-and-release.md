# 源码运行、Debug 与发布流程

本页是源码运行、开发和发布的唯一流程入口。滚动源码 Clone、显式前端 Debug、Windows ZIP 和
Docker image 是不同渠道，不能互相替代：

| 场景 | 读取的代码 | 是否 build | 用户入口 |
| --- | --- | --- | --- |
| 滚动源码 Clone | `server/src/` + 当前 production 前端 | 前端输入变化时自动 build | `DEEPAGENT_SHELL_PORT` |
| 显式前端 Debug | `frontend/` + `server/src/` | 否，使用 Vite HMR | 自动临时端口 |
| production 前端验证 | `frontend/` | 只生成 `frontend_dist/` | 不作为日常服务入口 |
| Windows ZIP | production 前端 + 当前 Python wheel + 自包含 runtime | 是 | ZIP 内 `start_server.bat` |
| Docker image | multi-stage build 中的当前前后端 | 是 | 容器 HTTP 端口 |

`server/src/deepagent_shell/frontend_dist/` 是被 Git 忽略的 production 输出。它不是源码，不提交 Git，
滚动 Clone 按输入指纹在需要时生成并由当前 Python 源码托管；正式发行物再把同一份前端冻结进 wheel。
前端仍只有根 `frontend/` 一份可编辑源码。

## 分支与源码通道

- `dev` 是日常活跃和滚动使用分支。每次推送仍必须是一项完整、可启动且经过相称验证的改动；不推送
  半成品。
- `main` 是已经在 `dev` 实际使用并确认稳定的源码。稳定晋升使用 merge/fast-forward，让两个长期
  分支重新汇合，不改写 `main` 历史。
- 更新 `main` 不等于发布。只有维护者明确决定发布时，才从 `main` 创建 `v<project.version>` tag；
  tag 才触发 Windows ZIP 和 Docker image。
- 紧急修复从 `main` 创建短期 `hotfix/*`，合并回 `main` 后立即再把 `main` 合并进 `dev`。代码结构
  已经变化时，在 `dev` 实现等价的用户行为修复，不机械复制补丁文本。

维护源码目录不作为用户实例运行。滚动用户使用独立 Clone 并固定跟踪 `dev`；该 Clone 自己的
`data/` 被 Git 忽略。停止服务后执行 `git pull --ff-only` 再重新启动，不在同一运行目录切换
`main/dev`，也不手工修改源码。

干净源码 checkout 不跟踪 `data/` 或 `runtime/`：前者由首次启动创建或由用户停机复制完整实例，
后者由 runtime 自举和应用启动按需创建。两者都不会通过 Git 分发或 pull 更新。

## 滚动源码 Clone

### 环境

- Windows 10/11 x64；
- Node.js 22（含 npm）；
- 首次准备自包含 Python/依赖时需要网络。

源码运行不使用宿主 Python 或 uv。根启动脚本复用项目 `runtime/app` 中的固定 CPython 和第三方
依赖，后端通过 `PYTHONPATH=server/src` 直接载入当前源码。Node.js 只用于 Clone 内按需生成
production 前端；正式 ZIP 用户不需要 Node.js。

### 启动

从仓库根运行：

```powershell
.\start_server.bat
```

`start_server.bat` 不根据分支名或源码目录进入 Debug。它使用 Clone 自己的
`data/config/deepagent-shell.env`，由同一个 Python 进程提供管理台、`/api/*` 和 `/v1/*`：

```text
浏览器 / OpenAI 客户端
  → 127.0.0.1:DEEPAGENT_SHELL_PORT
  → Python 当前 server/src
  → 当前 frontend_dist、/api、/v1
```

- 新实例当前默认端口为 19100；已有实例继续服从自己的配置，不静默改写。
- 首次运行或前端输入变化时，`prepare_source_frontend.ps1` 对锁定依赖执行必要的 `npm ci` 和
  `npm run build`；输入与产物均未变化时直接跳过。
- 每次启动先由 `bootstrap_runtime.ps1` 比较 Python 依赖、`server/uv.lock`、runtime lock 和 bootstrap
  脚本的组合指纹；指纹未变时直接复用，`git pull` 改变任一输入时自动重建并原子替换固定 runtime。
- Python 修改在停止并重新运行脚本后直接生效，不构建 wheel。
- `git pull --ff-only` 不改写被忽略的 `data/`、`runtime/`、`node_modules/` 或 `frontend_dist/`；启动
  指纹负责判断 runtime 和前端是否需要刷新。
- 正常源码运行不启动 Vite，不开放内部代理端口，也不显示 HMR 文案。

普通 Python、Vue、CSS、文档或配置逻辑修改不会改变 runtime 指纹，不重建 CPython 和第三方依赖。

## 显式前端 Debug

只有开发者正在连续修改 Vue、TypeScript 或 CSS、确实需要 Vite HMR 时，才显式调用 Debug 工具：

```powershell
$pythonHome = (Get-Content .\runtime\app\python-home.txt -Raw).Trim()
$python = Join-Path (Join-Path .\runtime\app $pythonHome) python.exe
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\packaging\development\start_dev.ps1 `
  -ProjectRoot $PWD `
  -PythonExe $python
```

工具让 Windows 分配两个不同且实际可绑定的 loopback 临时端口，创建本轮专用临时 data root、
临时管理密码和独立 API Key，并在控制台打印地址。停止后只关闭本轮后端并删除该临时 data；
它不读取或改写正常 Clone 的 `data/`。根 `start_server.bat` 永远不会自动调用它。

### 按风险验证

只运行与改动直接相关的最小门禁。常用命令：

```powershell
cd frontend
npm run lint
npm run typecheck
npm test
```

```powershell
cd server
uv run pytest ..\.test\<domain>\test_relevant_module.py -q
uv run python ..\.test\smoke_http.py
```

用户在线的普通布局、CSS 和局部前端改动默认先完成实现与代码级校验，然后交付并询问是否需要继续
测试；不因页面改动自动启动 Vite、浏览器或隔离后端。当前 Goal、用户明确要求测试或只有真实页面才能
判断的问题，再选择实看受影响页面。后端行为需要测试时使用最接近的 pytest。显式 Debug 用于实时
开发，`npm run build` 用于滚动 Clone 的正常运行、明确 production 验证和正式发布，完整发行仍是
另一流程。

### 实现与测试约定

- 主线优先、KISS。完整功能形成当前字段 contract、真实调用链、必要失败边界、少量直接测试和说明
  的闭环；不为未来兼容、升级或诊断预建平台。
- 当前 0.x 只维护现行结构。除非用户单独要求发布兼容，不增加旧字段双读、名称回退、兼容 wrapper、
  通用 schema migration 或版本矩阵；真实数据迁移需要单独授权的一次性脚本。
- 前端负责展示、表单状态、机械 payload 映射和请求编排；后端负责字段 contract、UUID、引用、权限、
  路径、物化和运行校验。新 capability 先完成领域对象、contract、manifest、专用 editor 和唯一真实
  runtime 链路，不提前建设通用表单或 registry。
- 永久测试按稳定领域放入 `.test/api_server/`、`.test/authoring/`、`.test/runtime/` 或
  `.test/security/`；根 `.test/` 不新增横跨多领域的综合 `test_*.py`。一个用例保护一个稳定行为，
  helper 留在职责最窄的领域。
- 新测试优先复用、调整或替换已有覆盖。单个测试文件接近 700 个物理行时，继续增加前先删除重复
  覆盖或按稳定职责拆分；源码文件超过 1000 行只先告警，不因数字本身顺手重构。
- 只运行最接近本次风险的最小范围。用户在线的普通改动默认先交付代码级校验结果，再询问是否继续
  测试；当前 Goal 可按风险自主验证。完整 pytest、浏览器点击、真实 Provider、长对话和多轮工具测试
  只用于明确发布门禁、实际风险或用户要求；`uv sync --extra dev` 只在依赖、锁或环境变化时运行。
- 验证以用户可观察行为、API 结果和持久化结果为准；源码结构检查只保护结构契约。验证后只清理本轮
  创建且路径已核实的进程、隔离数据、WAL/SHM、临时目录、截图和缓存。

Model Provider integration 属于发行版 runtime 依赖。新增或升级 Provider 时必须在
`server/pyproject.toml` 与 `server/uv.lock` 中统一解析，复验全部内置 Provider、Pydantic 版本和发行
notices；管理 API 与前端不得运行 pip/uv、写依赖文件或建立用户 overlay 环境。

## `dev` 晋升到 `main`

1. 用户确认当前 `dev` 的累计功能已经适合成为稳定源码。
2. 按累计改动风险运行最接近的前后端测试；已经得到充分覆盖的相同路径不重复建设门禁。
3. merge/fast-forward `dev` 到 `main`，确认两个长期分支重新汇合，再推送 `main`。
4. 普通稳定晋升到此结束，不构建 ZIP/Docker，也不创建 tag。

## 正式发布前

### 1. 更新版本

应用版本的权威字段是 `server/pyproject.toml` 中的 `project.version`。发布新版本时，同步检查当前
版本直接写入的位置：

- 由全局搜索找到的当前版本说明；
- 不把已经公开过的版本号用于不同构建。

Git tag 必须严格为 `v<project.version>`；两条 GitHub workflow 都会拒绝不匹配的 tag。

### 2. 检查待发布内容

在仓库根确认只包含本次预期修改：

```powershell
git status --short
git diff --check
uv run --project server python packaging/release/check_release_surface.py
```

发布面检查会拒绝任何进入源码面的 `data/`、`runtime/`、日志、secret、`.docs/`、用户 Skill 和宿主绝对路径。
稳定测试与构建代码属于公开源码，会随仓库发布。

### 3. 选择本地门禁

正式 tag 前确认 `dev -> main` 期间的相关验证仍有效，并运行第 2 步的轻量发布面检查。常规发行不在
本地重复 GitHub Actions 将执行的完整 ZIP 与 Docker 构建。

只有本轮修改了 Windows 打包、runtime bootstrap、依赖锁、启动入口、production 前端或发行物路径/
权限时，才从源码构建本地候选 ZIP；完整输入、产物、hash 和 moved smoke 见
[从源码构建 Windows 发行包](building-windows-release.md)。

只有本轮修改了 Dockerfile、Compose、容器启动或镜像运行边界时，才本地复验 Docker：

```powershell
docker build --platform linux/amd64 --tag deepagent-shell:release-test .
```

随后用一个可丢弃的独立 data 目录运行 `start_docker.ps1 -Image deepagent-shell:release-test`；不要复用真实
`data/`。其他常规版本由 tag workflow 在干净 runner 中完成两条发行构建和 smoke。正式 Docker
持久化与端口见 [Docker 部署](docker.md)。

### 4. 提交、推送和 tag

所有发布文件和版本修改提交后，先推送 `main`，再创建并推送 annotated tag：

```powershell
git status --short
git push origin main
git tag -a v<version> -m "release: v<version>"
git push origin v<version>
```

创建 tag 是正式发布动作。普通 push/PR 不运行 Windows ZIP 或 Docker image 的发布级 workflow；
`workflow_dispatch` 只做人工构建验证，不发布 image，也不会代替 tag 创建正式 Release。

## GitHub 自动发布结果

匹配版本的 `v*` tag 会同时触发：

- `windows-release.yml`：前端门禁、相关后端测试、源码发布面、自包含 ZIP、移动目录 smoke，随后把
  `deepagent-shell-windows-x64.zip` 和 `.sha256` 上传到该 GitHub Release；
- `container-release.yml`：secret scan、Linux amd64 image build/smoke，随后推送 GHCR 的完整版本、
  `major.minor` 和 `latest` tag；
- GitHub 自动提供该 tag 的 Source code ZIP/TAR，用户可以克隆或下载源码自行构建。

任何一个 workflow 失败都先修根因并提交新 commit；不要移动已有 tag 到另一提交。尚未对外使用时，
用下一个版本号重新发布仍比改写已公开 tag 更清楚。

## 发布后复验

1. 在 GitHub Actions 确认 Windows 与 Container 两个 job 都成功；
2. 从 Release 重新下载 Windows ZIP 和 `.sha256`，在本地核对：

   ```powershell
   Get-FileHash .\deepagent-shell-windows-x64.zip -Algorithm SHA256
   Get-Content .\deepagent-shell-windows-x64.zip.sha256
   ```

3. 解压到一个与仓库不同、可丢弃且最好包含空格的目录，运行包内 `start_server.bat`，确认首次设置、
   `/api/health`、数据库落点和移动后导入来源；
4. 拉取 `ghcr.io/fewnfds/deepdeepagent-shell:<version>`，使用独立宿主 data 目录确认启动、health 和持久化；
5. 确认 Release 同时有 Windows ZIP/hash、GitHub Source code ZIP/TAR，GHCR 有预期 tag。

本流程不要求日常开发重复扫描、哈希和压缩数千个 Python 文件。那部分只属于正式 Windows 发行包，
用于兑现普通用户无需安装 Python、Node、uv 或依赖的承诺。
