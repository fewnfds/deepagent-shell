# 开发与发布

## 运行通道

| 场景 | 后端 | 前端 | 入口 |
| --- | --- | --- | --- |
| 滚动源码 Clone | 当前 `server/src/` | 输入变化时自动 build | `start_server.bat` |
| 前端 Debug | 当前 `server/src/` | Vite HMR | `packaging/development/start_dev.ps1` |

`frontend/` 是唯一前端源码。`server/src/agent_shell/frontend_dist/` 是 Git 忽略的 production 产物。

## 分支

- `dev`：滚动源码与日常集成；每次推送保持可启动；
- `main`：经实际使用确认的稳定源码；由 `dev` merge/fast-forward 晋升；
- `v<project.version>` tag：从 `main` 创建，标记正式源码版本；
- `hotfix/*`：从 `main` 修复，合并回 `main` 后同步进 `dev`。

源码维护目录不作为用户实例运行。滚动用户使用独立 Clone，并保留该 Clone 自己的 `data/`。

## 源码运行

Windows 10/11 x64 需要 Node.js 22，不需要预装 Python。启动脚本按
`packaging/windows/runtime-lock.json` 在 `runtime/app` 准备固定的内置 CPython 3.12 和锁定依赖，后端直接
读取当前源码；前端输入变化时执行锁定的 npm build。项目只维护这套内置解释器，不声明兼容宿主 Python。

```powershell
.\start_server.bat
```

更新前停止服务：

```powershell
git pull --ff-only
.\start_server.bat
```

依赖和前端使用输入指纹刷新。普通 Python、文档或配置修改不会无条件重建整个 runtime。

停止服务后可以整体移动 Windows 运行 Clone。启动器根据自身位置重新解析源码、`data/` 和 `runtime/`；
`runtime/cache` 中的旧下载缓存可按需重建，不是安装位置契约。

自动化插件的 `requirements.txt` 不进入项目 `pyproject.toml`。Windows 启动器在核心 runtime 准备完成后，
单独按当前实例的插件需求指纹生成 `runtime/automation_plugins/site-packages`；输入未变化时复用。插件层只能
增加与核心锁兼容的二进制 wheel，不能修改 `runtime/app`。

## 当前运行时与依赖基线

当前发布基线由两个锁共同决定：`packaging/windows/runtime-lock.json` 锁定 Windows portable runtime，
`server/uv.lock` 锁定 Python wheel。当前稳定基线为：

| 层 | 当前版本 |
| --- | --- |
| 内置 CPython | `3.12.13` |
| runtime/CI uv | `0.12.2` |
| Deep Agents | `0.7.5` |
| FastAPI / Uvicorn | `0.141.1` / `0.52.1` |
| LangChain adapters | Anthropic `1.5.4`；DeepSeek `1.1.0`；Google GenAI `4.3.2`；Google Vertex AI `3.2.4`；OpenAI `1.4.1`；xAI `1.3.0` |
| LangChain core/graph | `langchain 1.3.14`；`langchain-core 1.5.3`；`langgraph 1.2.10` |
| 其他边界 | `packaging 26.3`；`websockets 15.0.1`；dev-only `httpx2/httpcore2 2.9.1` |

截至本基线，`uv lock --dry-run --upgrade` 不再产生可解析的锁变化。`uv tree --outdated` 仍可能显示
`websockets 17`、`protobuf 7`、`pydantic-core 2.48` 或 `pyarrow 25`，但它们分别受 LangGraph/Google
依赖范围或当前 Provider 组合约束；不得为了消除提示而放宽上游边界、删除 Provider 或改业务源码。新的
依赖升级应从重新运行上述 dry-run 开始，并按单一影响面批量推进。

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

推送 `dev` 或 `main` 时，GitHub Actions 运行一次无凭据的确定性门禁：前端 typecheck、UI policy 与
Vitest，以及后端 `.test/` 下由 pytest 默认收集的 `test_*.py`。本地需要复现完整门禁时使用：

```powershell
cd frontend
npm run typecheck
npm run ui:check
npm test
```

```powershell
cd server
uv run pytest ..\.test -q
```

`.test/smoke_http.py` 是显式进程/发行 smoke，不在默认 pytest 收集范围；真实 Provider 与 Agent eval 也不进入
日常门禁。普通局部修改仍只运行最接近的相关测试，完整门禁是分支集成入口，不是每次小改的固定本地流程。

## 发布

版本权威字段是 `server/pyproject.toml` 的 `project.version`。tag 必须为 `v<project.version>`。

发布前：

```powershell
git status --short
git diff --check
uv run --project server python packaging/release/check_release_surface.py
```

Python runtime 或前端生产依赖变化时，使用源码 runtime 重新生成并复核 `THIRD_PARTY_NOTICES.md`：

```powershell
uv run --project server python packaging/release/generate_third_party_notices.py `
  --runtime-root runtime/app --frontend-root frontend --output THIRD_PARTY_NOTICES.md
```

修改 Windows runtime bootstrap、依赖锁或启动入口时验证源码 Clone 启动。

确认 `main` 后创建 annotated tag：

```powershell
git push origin main
git tag -a v<version> -m "release: v<version>"
git push origin v<version>
```

已公开 tag 不移动；修复后更新项目版本并创建新 tag。
