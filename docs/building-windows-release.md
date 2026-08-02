# 从源码构建 Windows 发行包

普通用户不需要执行本页命令，应直接下载 GitHub Release 的 Windows ZIP。`git clone` 是开发、源码
审阅和自行构建渠道；正式 ZIP 已包含完整 runtime。

源码 checkout 中的 `start_server.bat` 使用自包含 Python 与依赖，后端直接运行当前 `server/src/`；
前端输入变化时只生成当前 production 管理台，不构建 DeepAgent Shell wheel 或发行包。Vite HMR 是另行
显式调用且使用隔离临时数据的开发工具。日常运行、Debug、版本、tag 和 GitHub Release 的完整顺序
见[源码运行、Debug 与发布流程](development-and-release.md)。
下面只说明 Windows 正式构建的细节；它会把当前前后端冻结进 ZIP。ZIP 不携带 `frontend/`、`server/src/` 或 Node.js，也
不会引用构建机器 checkout。

本页面向需要审阅或自行重建正式发行包的开发者。构建代码、版本锁、发布面检查、SBOM/许可证
生成器、便携 smoke 与 GitHub Actions 工作流都在公开仓库中，不依赖维护者本机文件或私有服务。

## 构建环境

- Windows 10/11 x64；
- Git；
- Node.js 22（含 npm）；
- Windows 自带的 Windows PowerShell；
- 首次下载依赖所需的网络和约 2 GiB 可用磁盘空间。

不需要预装 Python 或 uv。Node.js 只负责从 `frontend/package-lock.json` 重建管理台，不进入最终
运行依赖。

## 一条命令构建

从仓库根运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\build_portable.ps1
```

构建脚本按以下公开输入工作：

1. `npm ci`，再执行前端 strict typecheck 和 Vite production build；
2. 计算 Python/第三方依赖、runtime lock 和 bootstrap 脚本的组合 SHA-256 指纹；输入未变时直接
   复用已经校验的依赖 runtime；
3. 需要重建时，按 `packaging/windows/runtime-lock.json` 下载固定 uv，并校验该 ZIP 的 SHA-256；
4. 由固定 uv 安装精确 CPython 版本，并从 `server/uv.lock` 导出带哈希的 production requirements；
5. 只安装 Windows x64/Python 3.12 的二进制第三方依赖；
6. 每次发布单独快速构建当前非 editable DeepAgent Shell wheel，刷新依赖 runtime 中的应用层；
7. 删除 console wrapper、checkout `direct_url.json`、uv 绝对路径 junction 和第三方开发辅助资料；
8. 只把 Git 已跟踪的 `docs/` 和产品文件装入 staging；
9. 生成 SPDX 2.3 SBOM、第三方 notices/许可证原文和逐文件大小/SHA-256 manifest；
10. 检查源码与便携包发布面，再用 Windows 自带 `tar.exe` 生成 ZIP 和外部 SHA-256 文件。

第一次源码自举或 runtime 输入变化时，需要下载并安装完整便携 Python 和依赖，耗时取决于网络与
磁盘；这是一次性成本。相同输入下的普通启动和重复发布构建不会再次安装 runtime。需要排查损坏或
验证全新构建时才显式强制重建：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\packaging\windows\build_portable.ps1 `
  -RebuildRuntime
```

只修改了后端、文档或发行逻辑且已经在本轮生成最新的前端 production 产物时，可用
`-SkipFrontend` 跳过重复的 `npm ci` 和 Vite build；若产物不存在或陈旧，应用 wheel 构建会失败。
正式 CI 先从 lock 重建前端，再以 `-SkipFrontend` 避免在打包脚本中重复构建。

`server/pyproject.toml` 固定 wheel build backend；Python runtime、生产依赖和前端依赖分别由
`runtime-lock.json`、`server/uv.lock` 和 `frontend/package-lock.json` 约束。发行内容可从相同提交
重新构建；ZIP 容器时间戳可能使不同构建的 ZIP 字节哈希不同，外部 `.sha256` 始终对应本次正式产物。

## 构建结果

```text
release/deepagent-shell-windows-x64/          staging 目录
release/deepagent-shell-windows-x64.zip       便携发行包
release/deepagent-shell-windows-x64.zip.sha256
```

ZIP 内包含：

- 根 `start_server.bat`、`.env.example`、README 和 MIT `LICENSE`；
- `runtime/app/` 下的完整 Python、生产依赖与 DeepAgent Shell wheel；
- `docs/` 以及空的 `data/config`、`data/state`、`data/files`、`data/resources`、`data/logs`
  和运行态目录；
- `release-manifest.json`、`SBOM.spdx.json`、`THIRD_PARTY_NOTICES.md` 和
  `THIRD_PARTY_LICENSES/`。

它不包含真实 `data/config/deepagent-shell.env`、数据库、用户 Skill、未提交的本机 Tool/Middleware、`.docs/`、`.test/`、
源码目录、Node/Python 包缓存、日志或维护者路径。

验证外部 ZIP 哈希：

```powershell
Get-FileHash .\release\deepagent-shell-windows-x64.zip -Algorithm SHA256
Get-Content .\release\deepagent-shell-windows-x64.zip.sha256
```

在新解压的、可丢弃目录中验证首次设置、宿主环境隔离、健康检查和移动导入路径：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\packaging\release\smoke_portable.ps1 `
  -PortableRoot C:\tmp\deepagent-shell-windows-x64 `
  -Cleanup
```

## 更新依赖与 notices

修改任一 runtime 输入后，bootstrap 会按指纹自动重建。随后用公开生成器更新仓库根 notices：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\packaging\windows\bootstrap_runtime.ps1 `
  -ProjectRoot $PWD

$pythonHome = (Get-Content .\runtime\app\python-home.txt -Raw).Trim()
$python = Join-Path (Join-Path .\runtime\app $pythonHome) python.exe
$version = uv version --project .\server --short
& $python -I -B .\packaging\release\generate_release_metadata.py `
  --runtime-root .\runtime\app `
  --frontend-root .\frontend `
  --version $version `
  --notices .\THIRD_PARTY_NOTICES.md
```

正式构建会重新生成 staging notices 并与仓库根文件比较；不一致时直接失败，避免依赖已经变化但
许可证清单仍陈旧。

## CI 与 tag 发布

`.github/workflows/container-release.yml` 先在 Ubuntu runner 执行一次源码 secret scan，再构建并
smoke Linux image；`.github/workflows/windows-release.yml` 在 Windows runner 上执行前端门禁、
相关后端测试、源码发布面检查、完整 runtime/ZIP 构建和移动目录 smoke。两条发布级 workflow 只由
`v*` tag 或人工 `workflow_dispatch` 触发，普通 push/PR 不再重复构建发行物；只有与应用版本完全一致
的 tag 才把 ZIP 与 `.sha256` 直接发布到 GitHub Release。
