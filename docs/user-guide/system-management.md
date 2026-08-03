# 数据、文件与系统设置

## 实例数据

`data/` 是完整实例数据根：

```text
data/
  config/agent-shell.env
  state/agent-shell.sqlite3*
  files/
  resources/{skills,custom_tools,custom_middlewares}/
  logs/
```

它包含管理密码、API Key、Provider credential、配置、用户文件和历史，应作为敏感数据整体备份。
`runtime/` 只保存可重建运行态。

迁移时先完全停止服务或容器，再复制完整 `data/`，包括 SQLite 的 WAL/SHM。外部 filesystem 映射不在
`data/` 内，需要单独迁移并更新路径。

## 文件管理

【系统 / 文件管理】只开放四个 scope：普通文件、Skill、自定义工具和自定义 Middleware。支持浏览、
新建目录/文本文件、上传、下载、ZIP 打包、重命名、文本编辑和递归删除。

- 文本编辑上限 2 MiB，并使用 revision 防止静默覆盖；
- 二进制文件可以上传和下载，不能在线编辑；
- 文件操作不跟随符号链接或 Windows reparse point；
- 页面不能访问 `config/`、`state/`、`logs/`、外部映射或其他宿主路径；
- 递归删除没有回收站。

## 系统设置

【系统 / 系统配置】管理监听地址、端口、远程访问、管理密码、API Key、初始消息条数上限、拦截测试、
CORS origins 和可信代理 CIDR。secret 只显示是否配置，不回显明文。

API Key、消息上限和拦截测试保存后立即生效。host、端口、远程访问、管理密码、CORS 和可信代理写入
`data/config/agent-shell.env`，重启后生效。详细诊断和各类日志保存上限在【日志中心】管理。

远程部署要求见[安全与部署](../security-and-deployment.md)。
