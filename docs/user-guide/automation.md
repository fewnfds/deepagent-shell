# 使用自动化工作流

【自动化】让实例维护者把自定义 Python 脚本按顺序挂到 Primary 或 Subagent。它运行在 Agent 构造前和请求
生命周期外围，不是 LangChain Middleware，也不会包裹 model call 或 tool call。

## 1. 创建脚本

在【系统 / 文件管理 / 自动化脚本】下创建一个目录。目录名必须与脚本 ID 相同：

```text
automation_scripts/add-context/
  script.json
  main.py
```

`script.json`：

```json
{
  "api_version": 1,
  "id": "add-context",
  "name": "Add context",
  "description": "Append current instance context before Agent startup.",
  "triggers": ["hook"]
}
```

`triggers` 可包含 `hook`、`lifecycle` 或两者。`main.py` 必须使用 UTF-8，并在模块顶层准确提供一个异步入口：

```python
async def run(ctx) -> None:
    ctx.messages.append({
        "role": "user",
        "content": str(ctx.config.get("text", "")),
    })
```

扫描资源时只静态检查文件，不执行 `main.py`。脚本被有效 Agent 装配使用时才会 import；代码可引用服务当前
Python 环境已经安装的模块，平台不为脚本安装依赖或创建虚拟环境。

## 2. 创建工作流

在【自动化 / 事件工作流】或【定时工作流】新建配置。节点按页面顺序串行执行，每个节点选择脚本并填写一个
JSON object 作为 `ctx.config`。

事件工作流有三个固定 Hook：

| Hook | 次数 | 可用的阶段数据 |
| --- | --- | --- |
| `request_prepare` | 每个唯一 Primary/Subagent owner 一次 | `ctx.messages`、`ctx.initial_files`、Skill 准备 |
| `subagent_before_invoke` | 对应 Subagent 每次真实调用前一次 | 本次调用的 `ctx.messages` 副本 |
| `request_end` | 请求到达终态后每个 owner 一次 | `ctx.terminal`；定时任务已停止 |

定时工作流设置 `interval_seconds`。首轮在所有 Agent 构造成功后立即开始；一轮全部节点结束后才等待间隔，
不会重叠或补跑。某条定时流报错只停止该流，不会接管 Agent graph。

事件工作流至少要有一个节点，定时工作流至少要有一个节点。v1 没有 DAG、条件表达式、cron、自动重试或回滚；
复杂分支直接写在脚本中。

## 3. 装配 Agent

Primary 页面可分别选择一个事件工作流和一个定时工作流。Subagent 页面分别使用继承、替换或关闭：

- 继承：使用 Primary 最终选择的同类工作流；
- 替换：选择另一条工作流；
- 关闭：该 Subagent 不运行该类工作流。

同一个 Subagent 实体无论从多少分支或递归层级到达，在一次请求中都只有一套变量、Skill overlay 和定时任务。
每次实际调用它仍会执行一次 `subagent_before_invoke`。

## 消息修改接口

固定 Prompt Preset 已移除，但启动前插入或改写消息的通用接口保留：

- Primary 的 `request_prepare` 直接修改该 Primary 的 `ctx.messages`；
- 每个 Subagent 的 `request_prepare` 先准备自己的基础副本；
- 每次 `subagent_before_invoke` 再修改该次调用的新副本；
- 平台最后追加本次 delegated messages，脚本不能把委派任务挪到前面；
- Primary 和各 Subagent 的消息副本彼此独立。

脚本结束后的列表必须仍是有效的 OpenAI messages。生命周期运行中不会热注入新消息；需要动态信息时，把它
写到 mapped file，让 Agent 下一次 `read_file`、`grep` 或 `glob` 读取当时的磁盘内容。

## Context API

所有阶段都有：

- `ctx.config`：当前节点只读配置；
- `ctx.vars.get(path, default)`、`set(path, value)`、`delete(path)`；
- `ctx.request`、`ctx.agent`、`ctx.workflow`、`ctx.node`：只读标识；
- `ctx.paths.plugin_dir`：脚本目录；
- `ctx.paths.runtime_dir`：本次 request/owner 临时目录；
- `ctx.paths.mapped`：filesystem 虚拟映射路径到本地 `Path` 的只读映射；
- `ctx.tick`：定时轮次，其他阶段为 `None`；
- `ctx.terminal`：只在 `request_end` 提供；
- `ctx.log(value)`：写入截断后的自动化日志。

变量路径必须写全：`request.key`、`agent.key` 或 `workflow.key`。request 变量在本次请求全部 owner 间共享；
agent 变量只属于当前 Primary/Subagent 实体；workflow 变量属于当前 owner 的当前工作流。变量不会跨请求保留，
值必须可 JSON 序列化，单值上限 256 KiB。平台不做 merge、锁、事务或冲突处理。

`request_prepare` 还提供：

- `ctx.initial_files["/absolute/virtual/path"] = "text"`，值也可为 `bytes`；
- `ctx.prepare_skill(name, mode="overlay")`：返回本次 owner 的 Skill 副本目录；
- `ctx.prepare_skill(name, mode="persistent")`：返回原始 Skill 目录。

`overlay` 只影响本次请求并在终态清理；`persistent` 的修改会影响当前和未来请求。Skill 准备在其他 Hook 或
定时工作流中会被拒绝。

## 安全与冲突

自动化脚本以 Agent Shell 服务进程的完整权限执行，没有 sandbox。它可以访问网络、文件、环境和进程，也可能
删除或泄露实例与操作系统数据。只有实例维护者能管理这些资源，并应在运行前审查代码。

平台不协调脚本冲突：多个 owner 或工作流同时修改同一个文件或变量时，结果由真实执行时序决定。持久 Skill
修改也不备份、不回滚、不加锁。
