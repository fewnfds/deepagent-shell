# 开发与发布

## 运行通道

| 场景 | 后端 | 前端 | 入口 |
| --- | --- | --- | --- |
| 滚动源码 Clone | 当前 `server/src/` | 输入变化时自动 build | `start_server.bat` |
| 前端 Debug | 当前 `server/src/` | Vite HMR | `packaging/development/start_dev.ps1` |
| Windows ZIP | wheel | 已构建产物 | ZIP 内 `start_server.bat` |
| Docker | image 中的 wheel | 已构建产物 | 容器 HTTP 端口 |

`frontend/` 是唯一前端源码。`server/src/agent_shell/frontend_dist/` 是 Git 忽略的 production 产物。

## 分支

- `dev`：滚动源码与日常集成；每次推送保持可启动；
- `main`：经实际使用确认的稳定源码；由 `dev` merge/fast-forward 晋升；
- `v<project.version>` tag：从 `main` 创建，触发正式 Windows 与 Docker 发布；
- `hotfix/*`：从 `main` 修复，合并回 `main` 后同步进 `dev`。

源码维护目录不作为用户实例运行。滚动用户使用独立 Clone，并保留该 Clone 自己的 `data/`。

## 源码运行

Windows 10/11 x64 需要 Node.js 22。启动脚本在 `runtime/app` 准备固定 CPython 和锁定依赖，后端直接读取
当前源码；前端输入变化时执行锁定的 npm build。

```powershell
.\start_server.bat
```

更新前停止服务：

```powershell
git pull --ff-only
.\start_server.bat
```

依赖和前端使用输入指纹刷新。普通 Python、文档或配置修改不会无条件重建整个 runtime。

自动化插件的 `requirements.txt` 不进入项目 `pyproject.toml`。Windows 启动器在核心 runtime 准备完成后，
单独按当前实例的插件需求指纹生成 `runtime/automation_plugins/site-packages`；输入未变化时复用。插件层只能
增加与核心锁兼容的二进制 wheel，不能修改 `runtime/app`。

## 前端 Debug

只有需要 HMR 时使用隔离启动器。它分配临时 loopback 端口和临时 data，不读取正常实例数据：

```powershell
$pythonHome = (Get-Content .\runtime\app\python-home.txt -Raw).Trim()
$python = Join-Path (Join-Path .\runtime\app $pythonHome) python.exe
pwsh.exe -NoProfile -File .\packaging\development\start_dev.ps1 `
  -ProjectRoot $PWD -PythonExe $python
```

## 验证

按改动风险选择最接近的一项，不把所有检查固定串联：

```powershell
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

```powershell
cd server
uv run pytest ..\.test\<domain>\test_relevant_module.py -q
uv run python ..\.test\smoke_http.py
```

永久测试按职责放入 `.test/api_server/`、`.test/authoring/`、`.test/runtime/` 或 `.test/security/`。
用户可观察行为、API 和持久化结果是验收证据。

## 发布

版本权威字段是 `server/pyproject.toml` 的 `project.version`。tag 必须为 `v<project.version>`。

发布前：

```powershell
git status --short
git diff --check
uv run --project server python packaging/release/check_release_surface.py
```

只有修改 Windows 打包、runtime bootstrap、依赖锁、启动入口或 production 前端时才本地构建完整 ZIP；
只有修改 Dockerfile、Compose 或容器边界时才本地构建和运行 Docker。

确认 `main` 后创建 annotated tag：

```powershell
git push origin main
git tag -a v<version> -m "release: v<version>"
git push origin v<version>
```

tag workflow 构建 Windows ZIP/hash 与 Linux amd64 GHCR image。失败时修复后使用新版本，不移动已公开
tag。发布后从 Release 重新下载资产，核对 hash，并在可丢弃目录和独立 Docker data 上各做一次启动、
health 与持久化验证。
