# 数据、文件与系统设置

## 实例数据

`data/` 是完整实例数据根：

```text
data/
  config/
    components/<type>/<uuid>.yaml
    python_package_instances/{command,task-dispatcher,agent-middleware}/
    agents/main/<uuid>.yaml
    agents/subagent/<uuid>.yaml
    workflows/<uuid>.yaml
    system.yaml
    agent-shell.env
  state/agent-shell.sqlite3*
  files/
  resources/{skills,custom_tools}/
  templates/{workflow/command,workflow/task_dispatcher,agent/custom_middleware}/
  logs/security-events.jsonl
  logs/diagnostics/*.log
```

它包含管理密码、API Key、Provider credential、Workflow、Agent/组件配置、用户文件和历史，应作为敏感数据
整体备份。配置文件位于 `data/config/`；SQLite 保存官方 LangGraph checkpoint、Lifecycle Run Registry/Event Journal、
结构化 runtime 失败诊断和媒体元数据。迁移时先完全停止服务，
再复制完整 `data/`，包括 SQLite WAL/SHM。外部 filesystem 映射需要单独迁移并更新路径。

静态 Python 模板保存在 `data/templates/`，配置独占的 Python 扩展及其可选 `requirements.txt` 保存在
`data/config/python_package_instances/`。两者都属于需备份的 data；Windows 生成的共享依赖位于
`runtime/python_packages/`，属于可重建运行态，不进入备份。模板不运行且不参与依赖。

## 文件管理

【系统 / 文件管理】只开放四个 scope：普通文件、Skill、自定义工具和 Python templates。支持浏览、新建、
上传、下载、ZIP、重命名、文本编辑和递归删除。

Python templates scope 用于在 `workflow/command/`、`workflow/task_dispatcher/` 或 `agent/custom_middleware/` 类别中建档静态代码模板。
项目源码不携带实例 data，也不会自动生成默认模板；空模板目录不会影响运行中的配置扩展。

- 文本编辑上限 2 MiB，并使用 revision 防止静默覆盖；
- 文件操作不跟随符号链接或 Windows reparse point；
- 页面不能访问 `config/`（包括配置扩展目录）、`state/`、`logs/`、外部映射或其他宿主路径；
- 递归删除没有回收站。

## 系统设置

【系统 / 系统配置】管理监听地址、端口、远程访问、管理密码、API Key、初始消息条数上限、
LangSmith tracing、Endpoint、Project、可选 Workspace ID 与 write-only API Key，以及 CORS origins 和可信代理
CIDR。secret 只显示是否配置，不回显明文。启用 LangSmith 或修改连接字段时，系统会在保存前验证 API Key、
Endpoint 区域和 Workspace ID 是否匹配；验证失败时不保存本次修改。

LangSmith 配置项含义如下：

- 启用：控制是否向 LangSmith 发送 trace；
- 服务地址：LangSmith API Endpoint，按账号区域或自托管部署填写；
- 项目：接收 trace 的 LangSmith Project；
- Workspace ID：API Key 可访问多个 Workspace 时填写，否则留空；
- API Key：只写 secret；已配置的值不会回显，留空保存时保留原值。

API Key 和消息上限立即生效；host、端口、远程访问、管理密码、LangSmith、CORS 和可信代理重启后生效。

【系统 / 拦截消息】管理 Chat Completions 入站拦截。开关立即生效并持久化；开启后，请求在进入 Workflow
之前直接收到 OpenAI-compatible 的“消息已拦截”回复。页面只展示进程内最新一条原始 JSON，正文不写入 SQLite、
系统日志或运行诊断，服务重启后清空。
远程部署要求见[安全与部署](../security-and-deployment.md)。

【系统 / 日志中心】展示系统日志和运行失败诊断，不承载 Lifecycle、Run、checkpoint 或 Store 数据。运行诊断按可用范围
关联 request、Lifecycle、Run、parent Workflow 和当前 subject。正常完成不生成诊断。新异常的完整 exception chain
和 traceback 自动写入 `data/logs/diagnostics/`，写入成功时可从对应诊断行下载；日志中心不提供采集开关。
