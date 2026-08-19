# 编写 Python 扩展

本章覆盖 Output 脚本、Command、Task Dispatcher 和 Custom Middleware 的文件化 Python package，以及实例目录和依赖规则。

## Output 脚本

Agent Output Mode 与 Workflow Event Output 都是内联同步脚本，签名必须恰好为：

```python
def output(event):
    return event["message"]
```

Agent Output Mode 处理 Agent 事件；Workflow Event Output 只处理 Workflow-owned 非 Agent 事件。不要用它们修改 State、
做路由或隐藏顶层 HTTP error。应优先使用稳定的 `message`、`output`、`arguments`、`data_json` 字段；只有确实需要结构化
对象时才读取 `event["data"]`。

## 创建文件化 Python package

Command Node、Task Dispatcher 和 Custom Middleware 都是配置独占 Python package。创建自定义 Command 的最小 body
如下；其他 package 类型只替换 endpoint 和 `main.py` contract：

```http
POST /api/blocks/command

{
  "name": "Review command",
  "python_package": {
    "folder": "",
    "editable_files": ["main.py"]
  },
  "python_package_files": {
    "template_key": "__empty__",
    "revision": "",
    "files": [
      {"path": "main.py", "content": "<complete source>"}
    ]
  }
}
```

建议从经过审查的 template 创建；AI 已经拥有完整、符合 contract 的源码时也可以使用 `__empty__`。

首次保存后，系统会把模板复制成该配置独占的扩展目录：

```text
data/config/python_package_instances/
  command/<configuration-uuid>/
  task-dispatcher/<configuration-uuid>/
  agent-middleware/<configuration-uuid>/
```

前端和 Management API 只是创建、查看及保存这些文件的入口，不是唯一修改通道。创建完成后，可以直接在对应实例目录中维护
`main.py`、`requirements.txt`、本地模块和测试文件；不必为了修改扩展源码而改动 `frontend/`。直接新增的本地文件可以被正常
相对导入；若还要让组件编辑器显示该文件，应在编辑器的文件清单中加入其包内相对路径。

不要修改 Agent Shell 管理的 `package.json`，也不要移动、重命名扩展目录或让配置改为引用其他配置的目录。

这些代码在服务进程的受信任边界执行，没有 sandbox。Python 源码修改在下一次请求重新加载；`requirements.txt` 修改后必须
重启。若组件编辑页已在外部修改前打开，页面持有的 revision 会过期，应先重新载入组件再从页面保存，否则服务端会拒绝覆盖。

Command 和 Task Dispatcher 的工厂、返回结构及 Edge key 见[创建 Workflow Graph](03-workflow-graph.md)。Custom Middleware
必须返回一个官方 LangChain `AgentMiddleware`；完整 contract 见[文件化 Python 扩展](../middleware-packages.md)。

## Python 库与可用能力

AI 能理解 Python 和常见库的用法，但不能仅凭模型知识判断当前 Agent Shell 实例实际安装了哪些包、版本是否兼容或某个
传递依赖是否会一直存在。当前 Management API 也没有“枚举所有可 import 模块”的 endpoint。

必须把“可用库”作为显式输入告诉 AI：先给它当前模板返回的 `python_requirements` 和文件内容；新增库时让它同时修改该
配置独占的 `requirements.txt`。不要只说“环境里应该有某库”，也不要要求 AI 猜宿主 Python。AI 可以根据库的官方 API 写代码，
但实例是否可 import 只能由 dependency status 和真实运行证明。

| 来源 | 如何使用 |
| --- | --- |
| Python 3.12 标准库 | 可以直接 import；建议能用标准库完成时不增加依赖 |
| 平台公开 contract | 模板所需的 `langchain`、`langchain_core`、`langgraph`、`deepagents` 及文档明确展示的 `agent_shell` helper 可以使用；只调用公开、已文档化的 API |
| 当前 package 的本地模块 | 使用正常相对 import，例如 `from .helpers import build_tasks` |
| 其他第三方库 | 在当前配置扩展的 `requirements.txt` 中声明直接依赖，再重启并验证 |

不要因为某个库恰好是 FastAPI、Provider 或其他核心包的传递依赖就直接使用，也不要让 AI 根据训练数据猜版本。新增第三方
能力前，先确认该库支持 CPython 3.12、存在 Windows x64 wheel、与平台核心约束兼容，并在 `requirements.txt`
逐行写入普通 PyPI requirement。URL、本地路径、`.pth` 和只有源码发行包的依赖会被拒绝。

保存或 GET Python package 组件时，响应会投影：

- `dependency_status: "ready"`：当前 requirements 已准备完成，或没有额外依赖；
- `dependency_status: "restart_required"`：requirements 已变化，需要重启；
- `dependency_status: "failed"`：依赖解析或准备失败，结合 `dependency_error_code` 修正；
- `requirements_fingerprint`：当前依赖声明指纹，不是可用库清单。

依赖只从已启用 Workflow 可达的 Command、Dispatcher、Main Agent 和 Subagent 配置收集。最可靠的闭环是：声明直接依赖 ->
重启 -> GET 组件确认 `dependency_status` -> 调用一次真实 Workflow。AI 可以根据库的官方文档编写用法，但不能跳过这套实例验证。

下一步：只有需要异步子任务时阅读[使用后台 Run](05-background-runs.md)；否则直接进入
[验证、启用和真实调用](06-validation-and-references.md)。
