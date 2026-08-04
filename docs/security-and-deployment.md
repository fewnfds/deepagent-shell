# 安全与部署

## 认证

- 管理密码保护 `/admin` 与 `/api/*`；
- API Key 保护 `/v1/*`；
- 两者都必须是无空格的可打印 ASCII，均为 write-only；
- `/api/health` 用于存活探测，`/api/readiness` 返回分层就绪状态。

默认监听 `127.0.0.1`。监听非 loopback 地址前，必须在系统配置显式允许远程访问，并配置管理密码和
API Key。生产远程部署应由受信任反向代理提供 TLS、请求体限制、超时与访问控制。

## CORS 与代理

CORS 只接受明确的 `http://` 或 `https://` origin，不支持 `*`、userinfo、path、query 或 fragment。
可信代理使用精确 CIDR，并且只在远程访问模式下启用。不要信任未受控制的代理网段。

应用只依据当前安全配置解释转发信息。反向代理必须覆盖客户端可伪造的 forwarded headers，并把管理台
和推理 API 的访问策略一并纳入部署设计。

## Secret 与用户内容

Provider credential、API Key 和管理密码保存在实例 `data/` 中；当前 SQLite 不是加密 vault。保护整个
`data/` 的磁盘权限、备份和传输，不要提交 Git 或公开分享。

普通 API、DOM、系统日志和运行诊断不回显 credential、Bearer token、宿主敏感路径、traceback 或
Provider 原始错误正文。以下 management-only 功能会按产品用途保存用户内容：

- API 调用 RAW/DEBUG 下载；
- Provider 前拦截记录；
- 历史会话的客户端输入与最终响应；
- 用户创建的组件、文件和 Python 资源。

这些内容应按敏感数据处理。系统和运行日志只保存白名单 metadata；详细诊断也不保存逐 token 输出、
工具参数/结果或 reasoning 正文。

## 用户代码与文件系统

自定义工具、自定义 Middleware 和自动化插件是受信任的本地代码，真实请求会 import 或执行。只有实例维护者可以
管理这些资源，并应预先审查依赖、网络、文件和进程权限。

Windows 自动化插件可以声明公开 PyPI 的二进制 wheel 依赖。第三方 wheel 与插件代码具有相同的服务进程权限；
包名仿冒、恶意更新和依赖接管都属于供应链风险。平台固定公开 PyPI、拒绝 requirements 中的 URL/索引配置，
并约束核心版本，但这不代替维护者对包名、发布者、版本和许可证的审查。

自动化插件没有 sandbox，以 Agent Shell 服务进程权限运行。它可以修改消息、实例文件、持久 Skill、mapped
目录和服务账号可访问的其他宿主资源，也可以发起网络或进程操作。平台不备份、不回滚、不加锁，也不协调
多个插件的文件或变量冲突。

项目 filesystem 的 mapped directories 可读写宿主真实目录。只映射 Agent 确实需要的路径；写入、编辑
和递归删除工具按最小权限启用。Agent 看到的 Skill namespace 始终只读，但 automation prepare 可按用户选择
修改 Skill 源或本次 overlay。文件管理页面只访问五个 data scope，不代表
自定义代码或 mapped directory 具有相同限制。

## 容量与保留

部署者负责磁盘、内存、上传大小、外部映射和并发限制。文件管理文本编辑限制为 2 MiB；其他文件传输
采用流式处理，但不构成实例配额。API 调用、拦截、运行日志和历史会话使用可配置保存条数，系统日志
使用文件大小上限。降低上限会永久裁剪旧数据。

## 环境设置

主要启动字段位于 `data/config/agent-shell.env`：

```dotenv
AGENT_SHELL_HOST=127.0.0.1
AGENT_SHELL_PORT=19100
AGENT_SHELL_ALLOW_REMOTE=false
AGENT_SHELL_CORS_ORIGINS=[]
AGENT_SHELL_TRUSTED_PROXY_CIDRS=[]
AGENT_SHELL_MANAGEMENT_TOKEN=<management password>
```

未知 `AGENT_SHELL_*` 键会使启动失败。Windows 源码启动器读取当前 Clone 的 data 配置；源码和容器的
具体入口见根 README 与 [Docker 部署](docker.md)。
