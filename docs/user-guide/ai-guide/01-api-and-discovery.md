# 登录、对象关系与事实发现

配置工作以对象依赖、Management API 凭据、当前实例 catalog 和已有配置为基础。

## 对象关系

相关对象分为以下几层：

1. **Agent 组件**：模型、输出模式、Filesystem、系统提示词、Skill、权限、Custom Middleware 等。
2. **Agent 配置**：Main Agent 引用组件和 Subagent；Subagent 定义一层同步委派目标及 capability override。
3. **Workflow 组件**：Main Agent 自动成为 workflow 组件，其他组件通常需要编程。
3. **Workflow**：保存运转逻辑、运行限制，以及一份 Graph document。
4. **运行入口**：parent Workflow 被直接启用；开始通过 Graph 调用其他node、child runs。

## Management API 登录

默认管理地址是 `http://127.0.0.1:19100` 或查配置文件。
`/api/*` 使用 management token；`/v1/*` 使用另一把 API Key，两者不能互换。
实例使用自定义 data root 时，`agent-shell.env` 路径来自用户提供的实例信息，无需从源码中搜索。
默认 data root 下的 `data/config/agent-shell.env` 通常包含：

```dotenv
AGENT_SHELL_MANAGEMENT_TOKEN=<token>
```

`key` 是自动化查找配置项的稳定标识。命令可以只引用它，并保存在当前进程变量中，以 PowerShell 为例：

```powershell
$baseUrl = "http://127.0.0.1:19100"
$envFile = Join-Path (Get-Location) "data/config/agent-shell.env"
$tokenLine = Get-Content -LiteralPath $envFile |
    Where-Object { $_ -match '^AGENT_SHELL_MANAGEMENT_TOKEN=' } |
    Select-Object -First 1
if (-not $tokenLine) { throw "AGENT_SHELL_MANAGEMENT_TOKEN is missing" }
$managementToken = $tokenLine.Substring("AGENT_SHELL_MANAGEMENT_TOKEN=".Length)
$managementHeaders = @{ Authorization = "Bearer $managementToken" }

Invoke-RestMethod "$baseUrl/api/health"
Invoke-RestMethod "$baseUrl/api/readiness" -Headers $managementHeaders
```

## 当前事实入口

以下接口提供配置时需要的当前事实：

| 请求 | 用途 |
| --- | --- |
| `GET /api/catalog` | 当前组件类型、必选标志、Subagent 策略和编辑器默认值 |
| `GET /api/workflow-node-catalog` | 当前 Node type/version、`config_schema`、input/output handle 和允许角色 |
| `GET /api/blocks/{type}` | 某类现有组件及 UUID |
| `GET /api/main-agents`、`GET /api/subagents` | 现有 Agent 配置 |
| `GET /api/workflows?workflow_role=parent` | 现有 parent Workflow |
| `GET /api/python-package-templates/{kind}` | 当前脚本模板和只读内置示例 |
| `GET /api/validation/repository` | 当前完整配置仓库诊断 |

`{kind}` 当前为 `middleware`、`command` 或 `task-dispatcher`。catalog 是节点和组件类型的当前来源，模型记忆不是实例事实。

写操作通常沿以下数据流进行：

1. 新建依赖时由叶到根：组件 -> Subagent / Main Agent -> Workflow -> Graph -> Run。
2. Workflow 可保存为 `enabled: false` 草稿；只有正式保存通过完整校验后再修改 `enabled`。
3. 保存每次 POST 返回的 UUID；引用永远使用 UUID，不使用显示名称。
4. PUT 是完整可写对象更新，不是 PATCH。普通对象可从 GET 结果移除 `id` 后修改；
   模型 PUT 中的 `credential` 接受 `null`（同 Provider/Base URL 时保留旧 Key）或新的 write-only Key，不接受 GET 返回的脱敏 metadata；
   Python package 组件还要移除 manifest、dependency status、error 等只读投影，只提交 `name`、`python_package` 和当前 `python_package_files`。
   GET 投影含有只读字段，因此不能直接原样作为 PUT payload。
5. 422 响应中的结构化 issue/path 会指出不符合的字段；删除字段或降低约束不会替代对应修正。
6. 只要响应含 `X-Request-ID` 或 `request_id`，保留它用于诊断，但不要记录请求中的 secret 或用户隐私。

下一步：[创建组件并装配 Agent](02-components-and-agents.md)。
