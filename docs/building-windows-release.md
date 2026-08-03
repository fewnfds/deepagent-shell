# 构建 Windows 发行包

本页面向维护者。构建环境为 Windows 10/11 x64、Node.js 22、Git 和网络；无需预装 Python 或 uv。

```powershell
pwsh.exe -NoProfile -File .\packaging\windows\build_portable.ps1
```

脚本会：

1. 使用锁定 npm 依赖检查并构建 Vue production 前端；
2. 下载并校验锁定的 uv 与 CPython；
3. 按 `server/uv.lock` 安装生产依赖并构建 Agent Shell wheel；
4. 生成 license、third-party notices、SBOM 与 release manifest；
5. 组装并 smoke test 可移动的自包含目录；
6. 生成 `release/agent-shell-windows-x64.zip` 和 SHA-256。

ZIP 包含固定 CPython、生产依赖、应用 wheel、管理台、启动脚本、notices、SBOM 和 manifest。它不包含
源码开发环境、Node.js、uv cache、`data/` 或维护仓库的 `runtime/`。

ZIP 不预装实例自己的自动化插件依赖。启动器发现插件 `requirements.txt` 后，使用 runtime manifest 中固定的
uv 版本、下载地址和 SHA-256 获取 uv，并把兼容的二进制 wheel 原子安装到
`runtime/automation_plugins/site-packages/`。官方 ZIP 的 notices 与 SBOM 只覆盖发行包内置内容；实例维护者
负责审查运行时安装的插件包及其许可证。

修改 Python 依赖时先在 `server/pyproject.toml` 更新声明并刷新 `server/uv.lock`；修改 npm 依赖时同步
`frontend/package.json` 与 lockfile。依赖升级后检查 notices、SBOM 和所有内置 Provider。

正式发布由匹配 `server/pyproject.toml` 版本的 `v*` tag 触发 GitHub workflow。分支、门禁、tag 和发布后
验证见[开发与发布](development-and-release.md)。
