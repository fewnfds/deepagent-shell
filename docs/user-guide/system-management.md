# 数据、文件与系统设置

## 实例数据

`data/` 是完整实例数据根：

```text
data/
  config/agent-shell.env
  state/agent-shell.sqlite3*
  files/
  resources/{skills,custom_tools,custom_middlewares,automation_scripts}/
  logs/
```

它包含管理密码、API Key、Provider credential、配置、用户文件和历史，应作为敏感数据整体备份。
`runtime/` 只保存可重建运行态。

自动化插件的可选 `requirements.txt` 随插件保存在 `data/resources/automation_scripts/`；Windows 根据这些
声明生成的共享 Python 依赖层位于 `runtime/automation_plugins/`，不属于备份。恢复或迁移 data 后，在
Windows 上重新运行 `start_server.bat` 即可准备依赖。

迁移时先完全停止服务，再复制完整 `data/`，包括 SQLite 的 WAL/SHM。外部 filesystem 映射不在
`data/` 内，需要单独迁移并更新路径。

## 文件管理

【系统 / 文件管理】只开放五个 scope：普通文件、Skill、自定义工具、自定义 Middleware 和自动化脚本。支持浏览、
新建目录/文本文件、上传、下载、ZIP 打包、重命名、文本编辑和递归删除。

- 文本编辑上限 2 MiB，并使用 revision 防止静默覆盖；
- 二进制文件可以上传和下载，不能在线编辑；
- 文件操作不跟随符号链接或 Windows reparse point；
- 页面不能访问 `config/`、`state/`、`logs/`、外部映射或其他宿主路径；
- 递归删除没有回收站。

## 系统设置

【系统 / 系统配置】管理监听地址、端口、远程访问、管理密码、API Key、初始消息条数上限、拦截测试、
本项目 LangSmith 追踪、CORS origins 和可信代理 CIDR。secret 只显示是否配置，不回显明文。

API Key、消息上限和拦截测试保存后立即生效。host、端口、远程访问、管理密码、CORS 和可信代理写入
`data/config/agent-shell.env`，重启后生效。LangSmith 开关关闭时只在 Agent Shell 自己的进程边界内强制
禁用 LangSmith/LangChain tracing，不修改宿主机环境；开启后仍需用户自行提供 LangSmith 的 API Key、
Endpoint 等配置。详细诊断和各类日志保存上限在【日志中心】管理。

远程部署要求见[安全与部署](../security-and-deployment.md)。
